'use strict';
/**
 * kwfuse.js - the battery's power without the wait. eDrive Live reads it from the battery unit over diagnostics: a
 * few readings a second at best, each already a read old when it arrives, so a gauge on them alone steps behind the
 * car (Nov 9 2026: "super laggy, not usable"). The car's own signals come many times a second: the speed and the
 * longitudinal acceleration. From them the power at the wheels (mass x the acceleration the sensor feels, which takes
 * in the slope, plus rolling and air drag, x the speed), and from that, fitted continuously to eDrive Live's readings,
 * the battery's power now:
 *
 *   kW = a x P+ + b x P- + c          P+ / P-: the wheels' power when driving / regenerating (kW), c: everything else
 *                                     (climate, the 12 V side, the losses at rest)
 *
 * a, b and c are fitted by recursive least squares with forgetting on each eDrive Live reading, against the wheels'
 * power at the moment that reading was taken (kept in a short history), so the delay of the read doesn't enter the
 * fit. Shown: the fit applied to the wheels' power now. Only on electricity (the engine off): with the engine running
 * the battery is not what moves the car, and eDrive Live's reading is passed through as it is. Without a reading in
 * the last STALE_MS nothing is made up: none.
 *
 *   const f = createFuse();
 *   f.sample(t, { speed km/h, gLong g, engineOn });      every car sample (data.js: each data())
 *   f.measure(tTaken, kw);                              each new eDrive Live reading (the time it was read)
 *   f.now(t) -> { kw, fused, measuredKw, measuredAge } | null
 */
const G = 9.80665;
const MASS = 2600;            // kg: a G05 xDrive45e (2510 kg) with a driver and a little more
const CRR = 0.011;            // rolling resistance
const CDA = 0.95;             // m^2: drag area (Cd 0.33 x 2.9 m^2)
const RHO = 1.2;              // kg/m^3
const HIST_MS = 3000;         // the wheels' power kept this long, to look up the moment a reading was taken
const STALE_MS = 4000;        // eDrive Live silent this long: nothing shown
const LAMBDA = 0.985;         // forgetting per reading: about the last 60 readings count
const A_TAU_MS = 80;          // the acceleration's smoothing (its sensor is noisy at rest)

/** The power at the wheels (kW, + driving the car): speed km/h, the sensor's longitudinal acceleration in g. */
function wheelKw(speedKmh, gLong) {
    const v = Math.max(0, speedKmh) / 3.6;
    if (v < 0.3) return 0;
    const force = MASS * gLong * G + CRR * MASS * G + 0.5 * RHO * CDA * v * v;
    return force * v / 1000;
}

function createFuse(opts) {
    opts = opts || {};
    // theta = [a, b, c]: start as a typical drive train (85 % out, 70 % back) and 1.5 kW else
    let theta = [1 / 0.85, 0.7, 1.5];
    let P = [[0.05, 0, 0], [0, 0.05, 0], [0, 0, 4]];       // the fit's uncertainty (small: trust the start a while)
    const hist = [];                                        // [t, P+, P-, electric]
    let aAvg = null, aT = 0, meas = null, measT = 0, electric = false, fits = 0;
    const feat = (h) => [h[1], h[2], 1];

    function sample(t, s) {
        if (!s || typeof s.speed !== 'number' || typeof s.gLong !== 'number') return;
        aAvg = aAvg === null ? s.gLong : aAvg + (s.gLong - aAvg) * (1 - Math.exp(-Math.max(1, t - aT) / A_TAU_MS));
        aT = t;
        const w = wheelKw(s.speed, aAvg);
        electric = s.engineOn === false;
        hist.push([t, Math.max(0, w), Math.min(0, w), electric]);
        while (hist.length > 2 && t - hist[0][0] > HIST_MS) hist.shift();
    }
    /** The wheels' power at time t from the history (the nearest sample at or before it). */
    function at(t) {
        let best = null;
        for (let i = hist.length - 1; i >= 0; i--) { if (hist[i][0] <= t) { best = hist[i]; break; } }
        return best || hist[0] || null;
    }
    function measure(tTaken, kw) {
        if (typeof kw !== 'number' || !isFinite(kw)) return;
        meas = kw; measT = tTaken;
        const h = at(tTaken);
        if (!h || !h[3]) return;                            // (the engine running then: not a fit of the battery alone)
        // recursive least squares with forgetting
        const x = feat(h);
        const Px = P.map((r) => r[0] * x[0] + r[1] * x[1] + r[2] * x[2]);
        const den = LAMBDA + x[0] * Px[0] + x[1] * Px[1] + x[2] * Px[2];
        const K = Px.map((v) => v / den);
        const err = kw - (theta[0] * x[0] + theta[1] * x[1] + theta[2] * x[2]);
        theta = theta.map((v, i) => v + K[i] * err);
        P = P.map((r, i) => r.map((v, j) => (v - K[i] * Px[j]) / LAMBDA));
        // kept sensible: the drive train's efficiency between 50 and 100 %, back between 30 and 95 %
        theta[0] = Math.min(2, Math.max(1, theta[0]));
        theta[1] = Math.min(0.95, Math.max(0.3, theta[1]));
        theta[2] = Math.min(15, Math.max(-2, theta[2]));
        fits++;
    }
    function now(t) {
        if (meas === null || t - measT > STALE_MS) return null;
        const h = hist[hist.length - 1];
        // (the engine running, or no car samples: eDrive Live's reading as it is)
        if (!h || !electric || t - h[0] > 1000) return { kw: meas, fused: false, measuredKw: meas, measuredAge: t - measT };
        const x = feat(h);
        return { kw: theta[0] * x[0] + theta[1] * x[1] + theta[2] * x[2], fused: true, measuredKw: meas, measuredAge: t - measT };
    }
    return { sample, measure, now, fit: () => ({ a: theta[0], b: theta[1], c: theta[2], fits }) };
}

module.exports = { createFuse, wheelKw, MASS };

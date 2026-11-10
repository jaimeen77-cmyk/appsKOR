'use strict';
/**
 * test_engine.js - the engine with each layout against a recording stand-in for the cluster render client
 * (tools/scene.js): what is sent at the start and while driving, the start-up sweep, the fail-safe, the
 * centre left to the stock cluster, and that every shader's uniforms fit the service's limits.
 *   node tools/test_engine.js
 */
const assert = require('assert');
const path = require('path');
const { makeScene, APP } = require('./scene');
const { LAYOUTS } = require(path.join(APP, 'layouts'));
const font = require(path.join(APP, 'font'));

const RESERVED = ['u_mvp', 'u_mv', 'u_m', 'u_v', 'u_p', 'u_normal'];   // the renderer's matrix names (PROTOCOL.md)
let ok = 0;
const check = (name, fn) => { fn(); ok++; console.log('ok   ' + name); };
const drive = (s, seconds, fn) => { for (let i = 0; i < seconds * 25; i++) { s.setData(fn(i / 25)); s.engine._tick(); } };
const effects = (s) => Array.from(s.client.layers.values()).filter((l) => l.kind === 'effect');
const textsOf = (s) => s.engine._pieces().filter((p) => p.text !== null).map((p) => p.text);
const hard = (t) => ({ speed: 80 + 80 * Math.sin(t / 4), rpm: 2500 + 2000 * Math.sin(t * 2), stage: 'D', gear: 1 + Math.floor(t / 10) % 8, oil: 100 + t / 6, coolant: 90, mode: t > 30 ? 'S' : null });

LAYOUTS.forEach((L) => {
    const id = L.id;
    check(id + ': only shader layers on the panel; the only pixels are the glyph atlas', () => {
        const s = makeScene({ layout: id, data: { speed: 0, rpm: 800, stage: 'P', oil: 40, coolant: 40 } });
        const ls = Array.from(s.client.layers.values());
        assert(ls.every((l) => l.kind === 'effect' || l.kind === 'asset'));
        assert.strictEqual(ls.filter((l) => l.kind === 'asset').length, 1);
        assert(effects(s).every((l) => l.opts.target === 'panel' && l.opts.x >= 0 && l.opts.y >= 0 && l.opts.x + l.opts.w <= 1920 && l.opts.y + l.opts.h <= 720), 'inside the panel');
        effects(s).forEach((l) => {
            const n = Object.keys(l.uniforms).length, nums = Object.keys(l.uniforms).reduce((a, k) => a + l.uniforms[k].v.length, 0);
            assert(n <= 30 && nums <= 4096, 'uniforms ' + n);
            Object.keys(l.uniforms).forEach((k) => assert(l.uniforms[k].v.length <= 1024, k + ' over 1024 numbers'));
        });
        effects(s).forEach((l) => RESERVED.forEach((n) => assert(!new RegExp('(^|[^A-Za-z0-9_])' + n + '($|[^A-Za-z0-9_])').test(l.opts.fs), 'the shader uses ' + n + ', a RAMSES matrix semantic')));
        console.log('     start: ' + effects(s).length + ' layers, ' + s.client.messages + ' messages, ' + Math.round(s.client.bytes / 1024) + ' KB in all');
        assert(s.client.bytes < 600 * 1024);
        s.stop();
    });
    check(id + ': driving sends a few KB a second, no pixels', () => {
        const s = makeScene({ layout: id, data: {} });
        s.engine._tick();
        s.client.reset();
        drive(s, 60, hard);
        const perSec = s.client.bytes / 60;
        console.log('     driving: ' + Math.round(s.client.messages / 60) + ' messages/s, ' + (perSec / 1024).toFixed(1) + ' KB/s');
        assert(!s.client.log.some((m) => m.op === 'pixels' || m.op === 'layer'));
        assert(perSec < 16 * 1024);
        s.stop();
    });
    check(id + ': parked with nothing changing sends nothing (but an animated background\'s clock)', () => {
        const s = makeScene({ layout: id, data: {} });
        const still = () => ({ speed: 0, rpm: 0, stage: 'P', oil: 50, coolant: 50 });
        drive(s, 2, still);
        s.client.reset();
        drive(s, 10, still);
        const other = s.client.log.filter((m) => !(m.op === 'uniform' && m.name === 'u_time'));
        assert.strictEqual(other.length, 0, JSON.stringify(other.slice(0, 3)));
        s.stop();
    });
    check(id + ': the readings reach the cluster (gear, digits, values)', () => {
        const s = makeScene({ layout: id, data: {} });
        drive(s, 2, () => ({ speed: 50 * 1.609344, rpm: 2500, stage: 'D', gear: 3, oil: 100, coolant: 90 }));
        const t = textsOf(s);
        // (Sport shows the gear's number alone, as theirs: L.gearNumber)
        [L.gearNumber ? '3' : 'D3', '50'].forEach((x) => assert(t.indexOf(x) >= 0, x + ' in ' + JSON.stringify(t)));
        const vals = s.engine._pieces().filter((p) => p.value !== null).map((p) => p.value);
        // (on the scale's 160 mph, or a layout's own scale: L._speedFrac; M's and Sport's speed not a value: L.speedGauge)
        assert(L.speedGauge === false || vals.some((v) => Math.abs(v - 50) < 0.3 || Math.abs(v - 50 / 160) < 0.003 || (L._speedFrac && Math.abs(v - L._speedFrac(50)) < 0.003)), 'speed ' + vals);
        s.stop();
    });
    check(id + ': S on the selector shows S3', () => {
        const s = makeScene({ layout: id, data: {} });
        drive(s, 1, () => ({ speed: 60, rpm: 4000, stage: 'D', gear: 3, mode: 'S' }));
        assert(textsOf(s).indexOf(L.gearNumber ? '3' : 'S3') >= 0);
        s.stop();
    });
    check(id + ': centre left to the stock cluster: nothing over the middle', () => {
        const s = makeScene({ layout: id, options: { centre: 'stock' }, data: { speed: 0 } });
        s.engine._tick();
        // (a whole-view backdrop, M's and Sport's, with that area cut see-through: u_hole)
        const cutOut = (l) => /^(mdash|sdash)$/.test(l.kind) && l.params.u_hole && l.params.u_hole[0] <= 820 && l.params.u_hole[0] + l.params.u_hole[2] >= 1100;
        assert(!s.engine._pieces().some((l) => l.x < 1100 && l.x + l.w > 820 && !cutOut(l)), 'a piece over x 820-1100');
        s.stop();
    });
    check(id + ': map in the centre: nothing over the map window, the readings round it', () => {
        const C = require(path.join(APP, 'layout_common'));
        const s = makeScene({ layout: id, options: { centre: 'map' }, data: { speed: 0 } });
        s.engine._tick();
        // (the layout's own map window, M's and Sport's, else the native map area)
        const W = L.mapWindow || C.MAP, overMap = (r) => r.x < W.x + W.w && r.x + r.w > W.x && r.y < W.y + W.h && r.y + r.h > W.y;
        const over = s.engine._pieces().filter((l) => overMap(l));
        // a band's or a chevron's rectangle may reach into the window as long as what it draws stays out (a
        // chevron's ink: clearance.js): only those may overlap
        const { clashes } = require('./clearance');
        const o = { speedUnit: 'mph', tempUnit: 'f', centre: 'map', redline: 7000, rpmMax: 8000 };
        const hole = (l) => /^(mdash|sdash)$/.test(l.kind) && l.params.u_hole && l.params.u_hole[2] > 0;   // (cut see-through there)
        assert(over.every((l) => (l.geo && l.geo[2] > 0) || hole(l) || (l.kind === 'chevron' && clashes(l, o).indexOf('over the map') < 0)), 'over the map: ' + over.map((l) => l.key).join(' '));
        s.stop();
    });
    ['comfort', 'sport', 'efficient'].forEach((look) => check(id + ': ' + look + ' palette has every colour its pieces use', () => {
        const pal = L.palette(look);
        L.pieces({ speedUnit: 'mph', tempUnit: 'f', centre: 'info', redline: 7000, rpmMax: 8000 }).forEach((p) => {
            if (!p.colors) return;
            const c = p.colors(pal, { stage: 'D', gear: 3, oil: 90, coolant: 90 });
            Object.keys(c).forEach((k) => { const v = Array.isArray(c[k]) ? c[k][0] : c[k]; assert(/^#[0-9a-f]{6}$/i.test(v), p.key + '.' + k + ' = ' + v); });
        });
    }));
});

/*
 * Every layout is built around what the glass and the KOMBI keep for themselves: the camera's cowl, the dark box
 * the KOMBI leaves where its gear readout was, its eDrive readout's box, the slanted top corners and the warning
 * lights along the bottom. Every piece that draws something (not the backgrounds) stays clear of them; a dial
 * counts as its circle.
 */
const { clashes } = require('./clearance');
LAYOUTS.forEach((L) => ['info', 'map', 'stock'].forEach((centre) => ['phev', 'ice'].forEach((vehicle) => check(L.id + ' (' + centre + ', ' + vehicle + '): at most 60 pieces, all clear of the cowl, the KOMBI\'s boxes, the corners and the warning lights', () => {
    const ps = L.pieces({ speedUnit: 'mph', tempUnit: 'f', centre, redline: 7000, rpmMax: 8000, vehicle });
    assert(ps.length <= 60, ps.length + ' pieces: the renderer draws 64 layers an app');
    const bad = ps.map((p) => [p.key, clashes(p)]).filter(([, c]) => c.length).map(([k, c]) => k + ' ' + c.join(', '));
    assert(!bad.length, bad.join('; '));
}))));
/* Settings > Cluster: M car: the same, with the M KOMBI's two boxes in the middle; only a rev counter's own face
 * (layouts.M_ON_DIAL) may sit under them, since it can't move out of the middle */
const { M_ON_DIAL } = require(path.join(__dirname, '..', 'apps', 'cluster_layouts', 'layouts'));
LAYOUTS.forEach((L) => ['info', 'map', 'stock'].forEach((centre) => ['phev', 'ice'].forEach((vehicle) => check(L.id + ' (' + centre + ', ' + vehicle + ', M car): readings clear of the M KOMBI\'s boxes too', () => {
    const o = { speedUnit: 'mph', tempUnit: 'f', centre, redline: 7000, rpmMax: 8000, vehicle, cluster: 'm' };
    const ps = L.pieces(o);
    assert(ps.length <= 60, ps.length + ' pieces');
    const bad = ps.map((p) => [p.key, clashes(p, o).filter((c) => !(c === 'in an M box' && M_ON_DIAL.indexOf(p.key) >= 0))]).filter(([, c]) => c.length).map(([k, c]) => k + ' ' + c.join(', '));
    assert(!bad.length, bad.join('; '));
}))));

/* Settings > Layout: Bottom strip: the car's own: no background below CUT_Y but the black band, nothing small crossing it, and
 * the same readings clear of the KOMBI's boxes as without it */
const { CUT_Y, BG_Y, BG_NOTCH, BG_NOTCH_Y } = require(path.join(__dirname, '..', 'apps', 'cluster_layouts', 'layouts'));
LAYOUTS.forEach((L) => ['info', 'map', 'stock'].forEach((centre) => ['standard', 'm'].forEach((cluster) => check(L.id + ' (' + centre + ', ' + cluster + ', stock bottom strip): the layout ends at y ' + CUT_Y, () => {
    const o = { speedUnit: 'mph', tempUnit: 'f', centre, redline: 7000, rpmMax: 8000, vehicle: 'phev', cluster, bottomStrip: 'stock' };
    const ps = L.pieces(o);
    const low = ps.filter((p) => p.y + p.h > CUT_Y && !/^bgBand/.test(p.key) && (/^bg/.test(p.key) || p.kind === 'flat' || p.kind === 'panel' || p.kind === 'flag' || p.h <= 80));
    assert(!low.length, low.map((p) => p.key + ' ' + p.y + '+' + p.h).join(', '));
    // the black band below, to BG_Y, over the stock dials' edges, but not over the strip's drive mode and gear
    const band = ps.filter((p) => /^bgBand/.test(p.key));
    // the band to BG_Y, but over the drive mode and gear only to BG_NOTCH_Y (short of their tops at 660)
    assert(band.length === 3 && band.every((p) => p.y === CUT_Y && (p.x + p.w <= BG_NOTCH[0] || p.x >= BG_NOTCH[1] ? p.y + p.h === BG_Y : p.y + p.h === BG_NOTCH_Y && BG_NOTCH_Y < 660)), JSON.stringify(band.map((p) => [p.x, p.w, p.h])));
    assert(ps.some((p) => /^bg/.test(p.key)), 'a background still');
    const bad = ps.map((p) => [p.key, clashes(p, o).filter((c) => !(c === 'in an M box' && M_ON_DIAL.indexOf(p.key) >= 0))]).filter(([, c]) => c.length).map(([k, c]) => k + ' ' + c.join(', '));
    assert(!bad.length, bad.join('; '));
}))));

/* the car's own bottom strip, the readings in the centre: no range numbers (the strip shows both), the fuel
 * gauge bottom left (Retro: its own, in the speedometer) and the charge bottom right on a plug-in hybrid,
 * the dial layouts' dials centred (their centres either side of x 960, the same distance off it) */
LAYOUTS.forEach((L) => ['phev', 'ice'].forEach((vehicle) => check(L.id + ' (' + vehicle + ', stock bottom strip): the strip\'s ranges, gauges above them, centred', () => {
    const o = { speedUnit: 'mph', tempUnit: 'f', centre: 'info', redline: 7000, rpmMax: 8000, vehicle, cluster: 'standard', bottomStrip: 'stock' };
    const ps = L.pieces(o), keys = ps.map((p) => p.key);
    assert(!keys.some((k) => /^(fuel|elec|frange|erange)(Lbl|L)?$/.test(k)), 'range numbers: ' + keys.filter((k) => /fuel|elec|range/.test(k)).join(' '));
    // (Retro, M, Sport and Classic M: their own fuel gauges; M, Sport and Classic M their own charge, in their own look)
    assert.strictEqual(keys.indexOf('stripFuel') >= 0, L.stripFuel !== false && !L.ownStripGauges, 'fuel gauge');
    assert.strictEqual(keys.indexOf('stripSoc') >= 0, vehicle !== 'ice' && !L.ownStripGauges, 'charge gauge');
    assert(ps.length <= 60, ps.length + ' pieces');
    const dials = ps.filter((p) => (p.key === 'speed' || p.key === 'rpm') && p.kind === 'dial');
    if (dials.length === 2) {
        const c = dials.map((p) => p.x + p.w / 2);
        assert(Math.abs((c[0] + c[1]) / 2 - 960) < 2 && dials.every((p) => p.y + p.h <= CUT_Y), 'dials centred and above the strip: ' + c.join(' '));
    }
})));

/* 60 frames a second, a reading drawn within 5 ms: an update (every needle, bar and text of the layout) takes
 * well under 5 ms here; the unit's CPU is slower, so the budget asserted is 1.5 ms (worst 4 ms) on this machine */
LAYOUTS.forEach((L) => check(L.id + ': an update takes well under 5 ms (60 a second, drawn at once on a reading)', () => {
    const s = makeScene({ layout: L.id, data: {} });
    for (let i = 0; i < 30; i++) { s.setData(hard(i / 60)); s.engine._tick(); }   // warmed up
    const times = [];
    for (let i = 0; i < 600; i++) {
        s.setData(hard(i / 60));
        const t0 = process.hrtime.bigint();
        s.engine._full();     // the worst case: every needle, every text and colour at once
        times.push(Number(process.hrtime.bigint() - t0) / 1e6);
    }
    times.sort((a, b) => a - b);
    const avg = times.reduce((a, b) => a + b, 0) / times.length, p99 = times[Math.floor(times.length * 0.99)];
    console.log('     update: avg ' + avg.toFixed(3) + ' ms, 99% ' + p99.toFixed(3) + ' ms, worst ' + times[times.length - 1].toFixed(3) + ' ms');
    assert(avg < 1.5 && p99 < 4, 'avg ' + avg.toFixed(2) + ' ms, 99% ' + p99.toFixed(2) + ' ms');
    s.stop();
}));

check('start-up sweep: played by the cluster (one animation per needle and band), stopped after', () => {
    const s = makeScene({ layout: 'analog_sport', data: { speed: 0, rpm: 0 }, sweep: true });
    s.engine._tick();
    const anims = s.client.log.filter((m) => m.op === 'animate');
    assert(anims.length >= 4 && anims.every((a) => a.property === 'uniform' && a.name === 'u_value'));
    s.stop();
    assert(s.client.log.filter((m) => m.op === 'stop').length >= 4);
});

check('electric tach: the battery\'s power reaches the needle (past the rev scale\'s 8), regeneration below 0, scale from eDrive Live\'s ends', () => {
    const d = { speed: 40, rpm: 0, stage: 'D', driveMode: 'ELECTRIC', engineOn: false, kw: 55, kwOut: 120, kwIn: 50 };
    const s = makeScene({ layout: 'analog_sport', data: d });
    const tach = () => s.engine._pieces().find((p) => p.key === 'rpm');
    drive(s, 3, () => d);
    assert(Math.abs(tach().value - 55) < 0.5, 'drawing: ' + tach().value);
    const u = s.client.layers.get(tach().layer).uniforms;
    assert.deepStrictEqual(u.u_min.v, [-50]); assert.strictEqual(u.u_scale.v[0], 125); assert.deepStrictEqual(u.u_zero.v, [0.25]);
    drive(s, 3, () => Object.assign({}, d, { kw: -80 }));
    assert(Math.abs(tach().value + 50) < 0.5, 'regenerating, held at the limit: ' + tach().value);
    s.stop();
});

check('electric: Classic M\'s tach and Retro\'s economy gauge read the battery\'s power to its limits', () => {
    const d = { speed: 40, rpm: 0, stage: 'D', driveMode: 'ELECTRIC', engineOn: false, kw: 55, kwOut: 120, kwIn: 50 };
    const c = makeScene({ layout: 'classic', data: d });
    drive(c, 3, () => d);
    assert(Math.abs(c.engine._pieces().find((p) => p.key === 'rpm').value - 55) < 0.5);
    drive(c, 3, () => Object.assign({}, d, { kw: -30 }));
    assert(Math.abs(c.engine._pieces().find((p) => p.key === 'rpm').value + 30) < 0.5);
    c.stop();
    const h = Object.assign({}, d, { driveMode: 'HYBRID', engineOn: true, rpm: 1500, kw: -30 });
    const r = makeScene({ layout: 'retro', data: h });
    drive(r, 3, () => h);
    assert(Math.abs(r.engine._pieces().find((p) => p.key === 'econDial').value + 30) < 0.5);
    r.stop();
});

check('settle: shown only once wanted for a moment without a break (no flashing while the car comes up)', () => {
    let live = true;
    const s = makeScene({ data: { speed: 10 }, live: () => live, settleMs: 1200 });
    const now = Date.now, at = (ms) => { Date.now = () => now() + ms; s.engine._tick(); };
    try {
        at(0); assert(!s.engine.status().shown, 'not at once');
        at(600); live = false; at(700); live = true; at(800);
        at(1900); assert(!s.engine.status().shown, 'a break starts the wait again');
        at(2100); assert(s.engine.status().shown, 'shown after 1.2 s wanted');
    } finally { Date.now = now; s.stop(); }
});

check('fail-safe: hidden while the car data is not live, shown again when it is; off when disabled', () => {
    let live = true, on = true;
    const s = makeScene({ data: { speed: 10 }, live: () => live, enabled: () => on });
    const visible = () => effects(s).length > 0 && effects(s).every((l) => l.opts.visible === true);
    const hidden = () => effects(s).length === 0;
    s.engine._tick(); assert(visible());
    live = false; s.engine._tick(); assert(visible(), 'a moment\'s gap in the data keeps it (nothing dropped and resent)');
    const now = Date.now; Date.now = () => now() + 2000; s.engine._tick(); Date.now = now;
    assert(hidden(), 'stale data for longer hides it');
    live = true; s.engine._tick(); assert(visible());
    on = false; s.engine._tick(); assert(hidden(), 'off hides it');
    s.stop();
});

console.log(ok + ' passed');
process.exit(0);

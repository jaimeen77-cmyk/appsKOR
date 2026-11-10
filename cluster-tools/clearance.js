'use strict';
/**
 * clearance.js - what a layout's pieces must keep clear of on the glass (see the test in test_engine.js), and a
 * report of every clash: node tools/clearance.js
 */
require('./scene');
const path = require('path');
const C0 = require(path.join(__dirname, '..', 'apps', 'cluster_layouts', 'layout_common'));
/** What piece p clashes with. o: the layout's options (Settings > Cluster: M car adds the M KOMBI's two boxes). */
function clashes(p, o) {
    const C = C0, out = [];
    // (M's and Sport's whole-view backdrops, bimmer-lab's, count as backgrounds: over the car's strip their layer
    // ends at it, and the KOMBI's own boxes show over them)
    const isBg = /^bg|^boxBezel$/.test(p.key) || (p.kind === 'flat' && /bg/.test(String(p.colour || p.key))) || /^(mdash|sdash)$/.test(p.kind);
    if (isBg) return out;
    // a band along an arc (u_geo: centre in the layer, radius, thickness): the points of its ink, every 3 degrees
    const g = p.kind === 'band' && p.params && p.params.u_geo, sp = p.params && p.params.u_span;
    if (g && g[2] > 0 && sp) {
        const pts = [];
        const a0 = Math.min(sp[0], sp[1]), a1 = Math.max(sp[0], sp[1]);
        for (let a = a0; a <= a1; a += 3) for (const rr of [g[2] - g[3] / 2, g[2] + g[3] / 2]) {
            const t = a * Math.PI / 180; pts.push([p.x + g[0] + rr * Math.sin(t), p.y + g[1] - rr * Math.cos(t)]);
        }
        const inB = (b) => pts.some(([x, y]) => x > b.x && x < b.x + b.w && y > b.y && y < b.y + b.h);
        if (inB(C.NOTCH)) out.push('under the cowl');
        if (!C.strip(o) && inB(C.GEARBOX_HOLE)) out.push('in the gear box');
        if (!C.strip(o) && inB(C.EDRIVE_HOLE)) out.push('under the eDrive box');
        if (C.strip(o) && pts.some(([, y]) => y > C.STRIP_Y)) out.push('over the strip');
        if (C.mCar(o) && C.M_HOLES.some(inB)) out.push('in an M box');
        if (inB(C.TELLTALES)) out.push('over the warning lights');
        if (pts.some(([x, y]) => C.inCorner(x, y))) out.push('in a corner');
        return out;
    }
    // a chevron (two straight segments, A to B to C, in the layer): the points of its ink, every 6 px along it,
    // from its inner line out to its ticks, and its numerals (a box round each centre)
    if (p.kind === 'chevron' && p.params && p.params.u_ab) {
        const [ax, ay, bx, by] = p.params.u_ab, [cx0, cy0, T] = p.params.u_c, ln = p.params.u_lines || [0, 1000, 0, 1], mk = p.params.u_marks || [0, 0, 0, 0];
        const A = [p.x + ax, p.y + ay], B = [p.x + bx, p.y + by], Cp = [p.x + cx0, p.y + cy0], mid = [(A[0] + Cp[0]) / 2, (A[1] + Cp[1]) / 2];
        const inner = ln[1] < 500 ? T / 2 + ln[1] + ln[2] : T / 2, outer = T / 2 + ln[0] + (mk[0] ? 6 + mk[3] : 0);
        const pts = [];
        [[A, B], [B, Cp]].forEach(([P, Q]) => {
            const L = Math.hypot(Q[0] - P[0], Q[1] - P[1]), u = [(Q[0] - P[0]) / L, (Q[1] - P[1]) / L];
            let n = [-u[1], u[0]];
            if (n[0] * (mid[0] - P[0]) + n[1] * (mid[1] - P[1]) > 0) n = [-n[0], -n[1]];
            for (let s = 0; s <= L; s += 6) for (const off of [-inner, outer]) pts.push([P[0] + u[0] * s + n[0] * off, P[1] + u[1] * s + n[1] * off]);
        });
        // the numerals, at the marks (as the shader places them: out sideways; three figures wide)
        if (mk[0] && mk[1]) {
            const L1 = Math.hypot(B[0] - A[0], B[1] - A[1]), L2 = Math.hypot(Cp[0] - B[0], Cp[1] - B[1]);
            const nrm = (P, Q) => { const L = Math.hypot(Q[0] - P[0], Q[1] - P[1]); let n = [-(Q[1] - P[1]) / L, (Q[0] - P[0]) / L]; if (n[0] * (mid[0] - P[0]) + n[1] * (mid[1] - P[1]) > 0) n = [-n[0], -n[1]]; return n; };
            const n1 = nrm(A, B), n2 = nrm(B, Cp);
            for (let m = 0; m <= mk[0]; m++) {
                const sm = m / mk[0] * (ln[3] > 0 ? ln[3] : 1) * (L1 + L2), on1 = sm <= L1;
                const pm = on1 ? [A[0] + (B[0] - A[0]) * sm / L1, A[1] + (B[1] - A[1]) * sm / L1] : [B[0] + (Cp[0] - B[0]) * (sm - L1) / L2, B[1] + (Cp[1] - B[1]) * (sm - L1) / L2];
                const nu = p.params.u_nums || [0, 0, 0, 0], c = [pm[0] + (n1[0] + n2[0] >= 0 ? 1 : -1) * mk[2], Math.max(pm[1], p.y + nu[3])], hh = mk[1] / 2, hw = mk[1] * 1.35;
                pts.push([c[0] - hw, c[1] - hh], [c[0] + hw, c[1] - hh], [c[0] - hw, c[1] + hh], [c[0] + hw, c[1] + hh]);
            }
        }
        const inB = (b) => pts.some(([x, y]) => x > b.x && x < b.x + b.w && y > b.y && y < b.y + b.h);
        if (inB(C.NOTCH)) out.push('under the cowl');
        if (!C.strip(o) && inB(C.GEARBOX_HOLE)) out.push('in the gear box');
        if (!C.strip(o) && inB(C.EDRIVE_HOLE)) out.push('under the eDrive box');
        if (C.strip(o) && pts.some(([, y]) => y > C.STRIP_Y)) out.push('over the strip');
        if (C.mCar(o) && C.M_HOLES.some(inB)) out.push('in an M box');
        if (inB(C.TELLTALES)) out.push('over the warning lights');
        if (pts.some(([x, y]) => C.inCorner(x, y))) out.push('in a corner');
        if (o && o.centre === 'map' && inB(C.MAP)) out.push('over the map');
        return out;
    }
    const round = p.kind === 'dial' || p.kind === 'e9x';
    const cx = p.x + p.w / 2, cy = p.y + p.h / 2, r = Math.min(p.w, p.h) / 2;
    const hit = (b) => (round
        ? (() => { const nx = Math.max(b.x, Math.min(cx, b.x + b.w)), ny = Math.max(b.y, Math.min(cy, b.y + b.h)); return (nx - cx) ** 2 + (ny - cy) ** 2 < (r - 6) ** 2; })()
        : p.x < b.x + b.w && p.x + p.w > b.x && p.y < b.y + b.h && p.y + p.h > b.y);
    if (hit(C.NOTCH)) out.push('under the cowl');
    // with the car's own bottom strip the KOMBI shows neither box (layout_common.STRIP_Y)
    if (!C.strip(o) && hit(C.GEARBOX_HOLE)) out.push('in the gear box');
    if (!C.strip(o) && hit(C.EDRIVE_HOLE)) out.push('under the eDrive box');
    if (C.strip(o) && !round && p.y + p.h > C.STRIP_Y) out.push('over the strip');
    if (C.strip(o) && round && cy + r - 6 > C.STRIP_Y + 4) out.push('over the strip');
    if (C.mCar(o) && C.M_HOLES.some(hit)) out.push('in an M box');
    if (hit(C.TELLTALES)) out.push('over the warning lights');
    const pts = round ? [[cx - r * 0.7, cy - r * 0.7], [cx + r * 0.7, cy - r * 0.7], [cx, cy - r]] : [[p.x, p.y], [p.x + p.w, p.y]];
    if (pts.some(([x, y]) => C.inCorner(x, y))) out.push('in a corner');
    return out;
}
module.exports = { clashes };

if (require.main === module) {
    const { LAYOUTS } = require(path.join(__dirname, '..', 'apps', 'cluster_layouts', 'layouts'));
    let n = 0;
    LAYOUTS.forEach((L) => ['info', 'map', 'stock'].forEach((centre) => ['phev', 'ice'].forEach((vehicle) => [['standard', 'stock'], ['standard', 'layout'], ['m', 'layout']].forEach(([cluster, bottomStrip]) => {
        const o = { speedUnit: 'mph', tempUnit: 'f', centre, redline: 7000, rpmMax: 8000, vehicle, cluster, bottomStrip };
        L.pieces(o).forEach((p) => {
            const c = clashes(p, o);
            if (c.length) { n++; console.log(L.id + ' ' + centre + ' ' + vehicle + ' ' + cluster + (bottomStrip === 'stock' ? ' strip' : '') + ': ' + p.key + ' (' + p.kind + ' ' + [p.x, p.y, p.w, p.h].map(Math.round).join(',') + ') ' + c.join(', ')); }
        });
    }))));
    console.log(n ? n + ' clashes' : 'all clear');
}

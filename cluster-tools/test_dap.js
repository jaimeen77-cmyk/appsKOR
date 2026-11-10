'use strict';
/**
 * test_dap.js - the driving assistant's feed for Modern wide's road (apps/cluster_layouts/dap.js): the cruise
 * control, the steering assist, the warnings and the object list decoded from names or numbers however the
 * binding wraps them, the cars picked for the picture, and the subscriptions: node tools/test_dap.js
 */
const assert = require('assert');
const path = require('path');
const D = require(path.join(__dirname, '..', 'apps', 'cluster_layouts', 'dap.js'));
let ok = 0;
const check = (name, fn) => { fn(); ok++; console.log('ok   ' + name); };

check('cruise control: on with its set speed and gap; off when nothing is set', () => {
    const a = D.decodeIbVip({ assistedDrivingViewFunctionInputIbVip: { assistedDrivingViewStateXcc: 3, assistedDrivingViewDispXcc: 70, assistedDrivingViewDispGapChoice: 3, assistedDrivingViewACCTargetObjectId: 12 } });
    assert.deepStrictEqual([a.on, a.set, a.gap, a.target], [true, 70, 3, 12]);
    const b = D.decodeIbVip({ assistedDrivingViewStateXcc: 0, assistedDrivingViewDispXcc: 0 });
    assert.deepStrictEqual([b.on, b.set], [false, null]);
});
check('steering assist: holding the lane by name or number, standby is not', () => {
    assert.strictEqual(D.decodeLateral({ lsaFunctionStates: { lsaState: 'FOLLOW_LANE' } }), true);
    assert.strictEqual(D.decodeLateral({ lsaFunctionStates: { lsaState: 14 } }), true);
    assert.strictEqual(D.decodeLateral({ lsaFunctionStates: { lsaState: 'ACTIVE_STANDBY' } }), false);
    assert.strictEqual(D.decodeLateral({ lsaFunctionStates: { lsaState: { name: 'HOO_FOLLOW_LANE', value: 15 } } }), true);
});
check('warnings: lane departure left, lane change right', () => {
    const l = D.decodeLca({ statusLaneDepartureWarning: { directionLaneDepartureWarning: 'WARNING_LEFT' }, statusLaneChgWarning: { statusLaneChangeWarningRight: 'WARNING_RIGHT', statusLaneChangeWarningLeft: 'NO_WARNING_LEFT' } });
    assert.deepStrictEqual(l, { ldw: { left: true, right: false }, lcw: { left: false, right: true } });
    assert.deepStrictEqual(D.decodeLca({ directionLaneDepartureWarning: 3 }).ldw, { left: true, right: true });
});
const obj = (id, x, y, lane, brake) => ({ objectID: id, objectPosition: { x, y }, objectPrediction: { laneAssignment: lane }, objectProperties: { brakeLight: brake || 'KBRAKELIGHTSTATUS_OFF' } });
check('objects: metres from the configured scale, behind and far ones left out', () => {
    const list = D.decodeObjects({ suAARObjectList: { objectList: [obj(1, 3800, 20, 'EGO'), obj(2, -500, 0, 'EGO'), obj(3, 2200, 360, 2, 'KBRAKELIGHTSTATUS_ONREGULAR')] } }, { posScale: 0.01 });
    assert.deepStrictEqual(list.map((o) => [o.id, o.x, o.lane]), [[1, 38, 0], [3, 22, 1]]);
    assert.strictEqual(list[1].brake, true);
});
check('the picture: the cruise target followed, else the nearest in the lane; the nearest each side', () => {
    const list = [{ id: 1, x: 60, y: 0, lane: 0 }, { id: 2, x: 30, y: 0, lane: 0 }, { id: 3, x: 12, y: 3.5, lane: 1 }, { id: 4, x: 4, y: -3.5, lane: -1 }, { id: 5, x: 80, y: -3.5, lane: -1 }];
    let p = D.pick(list, 1);
    assert.deepStrictEqual([p.lead.id, p.left.id, p.right.id], [1, 3, 4]);
    p = D.pick(list, 0);
    assert.strictEqual(p.lead.id, 2);
    p = D.pick([{ id: 9, x: 20, y: 0.3, lane: null }], 0);
    assert.strictEqual(p.lead.id, 9, 'no lane assignment: by its offset');
});
check('subscriptions: the four events, declared in app.json; the state dropped 3 s after the last event', () => {
    const app = require(path.join(__dirname, '..', 'apps', 'cluster_layouts', 'app.json'));
    Object.keys(D.SERVICES).forEach((i) => assert.deepStrictEqual(app.signals[i]._broadcasts, [D.SERVICES[i]], i));
    const handlers = {};
    const ctx = { spec: { config: app.config }, signals: { watch: (iface, inst, h) => { Object.assign(handlers, h); return Promise.resolve({}); } } };
    const logs = [];
    const dap = D.startDap(ctx, { info: (m) => logs.push(m), warn: () => {} });
    assert.strictEqual(dap.state(), null);
    handlers.assistedDrivingViewFunctionInputIbVip({ assistedDrivingViewStateXcc: 2, assistedDrivingViewDispXcc: 65, assistedDrivingViewDispGapChoice: 2 });
    handlers.suAARObjectList({ objectList: [obj(1, 2500, 0, 'EGO')] });
    const s = dap.state();
    assert(s && s.acc.on && s.acc.set === 65 && s.lead && s.lead.x === 25, JSON.stringify(s));
    assert(logs.some((m) => /^dap raw ibvip/.test(m)) && logs.some((m) => /^dap raw objects/.test(m)), 'raw values logged');
    s.at -= 4000;
    assert.strictEqual(dap.state(), null, 'stale');
});
check('the road moves with the car: the dashes by the distance driven, the cars glide between updates', () => {
    require('./scene');   // (the kit's runtime for the layouts)
    const L = require(path.join(__dirname, '..', 'apps', 'cluster_layouts', 'layouts.js')).byId('modern_wide');
    const road = L.pieces({ centre: 'info', bottomStrip: 'stock', vehicle: 'phev', speedUnit: 'mph' }).find((p) => p.key === 'road');
    assert(road && typeof road.frame === 'function', 'a frame hook');
    const f = road.frame, D0 = Object.assign({}, D.DEMO);
    let u = f({ speed: 0, dap: D0 }, 16);
    assert.strictEqual(u.u_run[0], 0, 'standing still: the dashes stand still');
    for (let i = 0; i < 60; i++) u = f({ speed: 100, dap: D0 }, 1000 / 60);          // a second at 100 km/h
    assert(Math.abs(u.u_run[0] - 27.78) < 0.05, '27.8 m in a second at 100 km/h: ' + u.u_run[0]);
    const near = u.u_lead[1];
    u = f({ speed: 100, dap: Object.assign({}, D0, { lead: { x: 10, y: 0, brake: false } }) }, 16);   // the lead car jumps from 38 m to 10 m
    assert(u.u_lead[1] > near && u.u_lead[1] < 1 / (1 + 10 / 16), 'part of the way in one frame: ' + near + ' -> ' + u.u_lead[1]);
    for (let i = 0; i < 60; i++) u = f({ speed: 100, dap: null }, 16);
    assert.deepStrictEqual([u.u_lead[0], u.u_side[0], u.u_side[1]], [0, 0, 0], 'gone with the assistant');
});
console.log(ok + ' passed');

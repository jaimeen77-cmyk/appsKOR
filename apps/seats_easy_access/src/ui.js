'use strict';
const { ComfortClient, EasyAccess, VERSION, bounded } = require('./core');

async function run(options) {
    const opts = options || {}, sdk = opts.sdk || require('oap-sdk');
    const app = new sdk.OnlineApp();
    const client = opts.client || new ComfortClient();
    const easy = new EasyAccess(client);
    const active = () => Promise.resolve(app.registerActive()).catch(() => {});
    app.on('appStatusProxyReady', active);
    let main, timer, closing = false, visible = false, focused = false;

    async function close() {
        if (closing) return;
        closing = true; clearInterval(timer); easy.setForeground(false);
        await bounded(client.send({ op: 'stop' }), 900, 'stop timeout').catch(() => {});
        client.close();
    }
    app.on('shutdown', () => close().then(() => { if (!opts.noExit) process.exit(0); }));
    await app.start(); await active();
    const rhmi = app.rhmiApplication;
    if (!rhmi) return { app: app, easy: easy, close: close };
    const comp = (name) => rhmi.getByName(name);
    const cache = {};
    function text(name, value, cell) {
        const c = comp(name), key = name + ':' + (cell || 'Text'), string = String(value);
        if (!c || cache[key] === string) return;
        cache[key] = string;
        Promise.resolve(c.setValue(0, cell || 'Text', string, 'Text')).catch(() => { delete cache[key]; });
    }
    function enable(name, value) {
        const c = comp(name);
        if (c) Promise.resolve(c.setProperty('Enabled', value ? 1 : 0, 'UInt')).catch(() => {});
    }
    function seatText(who) {
        const state = easy.state();
        if (!state) return '상태 없음';
        const axes = state.seats.axes[who];
        if (!axes.length) return '지원되는 시트 모듈 없음';
        const exit = state.seats.exit[who] ? '하차 위치 저장됨' : '하차 위치 미저장';
        return exit + ' · ' + axes.join('/');
    }
    function draw() {
        const state = easy.state();
        const moving = state && (state.seats.moving || state.seats.job);
        const who = easy.selectedSeat;
        const axes = state ? state.seats.axes[who] : [];
        text('STATUS', easy.message);
        text('SELECTED', who === 'driver' ? '운전석' : '조수석', 'Text2ndCol');
        text('SELECT_DRIVER', who === 'driver' ? '● 운전석' : '운전석');
        text('SELECT_PASSENGER', who === 'passenger' ? '● 조수석' : '조수석');
        text('AUTO', state ? (state.settings.easyExit ? '켜짐' : '꺼짐') : '확인 필요', 'Text2ndCol');
        text('DRIVER', seatText('driver'), 'Text2ndCol');
        text('PASSENGER', seatText('passenger'), 'Text2ndCol');
        text('VEHICLE', state ? (state.parked ? '정차' : '주행 중') + (moving ? ' · 시트 이동 중' : '') : '알 수 없음', 'Text2ndCol');
        const ready = easy.foreground && !!state && !easy.pending;
        enable('REFRESH', easy.foreground && !easy.pending);
        enable('SELECT_DRIVER', easy.foreground && !easy.pending && !easy.moving);
        enable('SELECT_PASSENGER', easy.foreground && !easy.pending && !easy.moving);
        enable('AUTO_TOGGLE', ready);
        ['SLV_MINUS', 'SLV_PLUS', 'SHV_MINUS', 'SHV_PLUS', 'LNV_MINUS', 'LNV_PLUS',
            'SNV_MINUS', 'SNV_PLUS', 'KHV_MINUS', 'KHV_PLUS'].forEach((name) => {
            enable(name, ready && axes.indexOf(name.slice(0, 3)) >= 0 && !easy.actionReady(who, false));
        });
        enable('MEMORY_SAVE', ready && !easy.actionReady(who, true));
        enable('M1', ready && !easy.actionReady(who, true));
        enable('M2', ready && !easy.actionReady(who, true));
        enable('M3', ready && !easy.actionReady(who, true));
        enable('EXIT_SAVE', ready && !easy.actionReady(who, true));
        enable('EXIT_MOVE', ready && state.seats.exit[who] && !easy.actionReady(who, true));
        text('MAKE_ROOM', state && state.seats.roomOut ? 'Make room · 조수석 원위치 복귀' : 'Make room · 조수석 공간 확보');
        enable('MAKE_ROOM', ready && who === 'passenger' && !easy.actionReady('passenger', true));
        enable('STOP', easy.foreground && !!state);
    }
    function action(name, handler) {
        const c = comp(name);
        if (c) c.on('action', () => Promise.resolve().then(handler).catch((error) => {
            easy.message = error.message; easy.emit('change');
        }));
    }
    action('REFRESH', () => easy.refresh());
    action('AUTO_TOGGLE', () => easy.toggle());
    action('SELECT_DRIVER', () => easy.selectSeat('driver'));
    action('SELECT_PASSENGER', () => easy.selectSeat('passenger'));
    action('SLV_MINUS', () => easy.jog('SLV', -1)); action('SLV_PLUS', () => easy.jog('SLV', 1));
    action('SHV_MINUS', () => easy.jog('SHV', -1)); action('SHV_PLUS', () => easy.jog('SHV', 1));
    action('LNV_MINUS', () => easy.jog('LNV', -1)); action('LNV_PLUS', () => easy.jog('LNV', 1));
    action('SNV_MINUS', () => easy.jog('SNV', -1)); action('SNV_PLUS', () => easy.jog('SNV', 1));
    action('KHV_MINUS', () => easy.jog('KHV', -1)); action('KHV_PLUS', () => easy.jog('KHV', 1));
    action('MEMORY_SAVE', () => easy.armMemorySave());
    action('M1', () => easy.memory(0)); action('M2', () => easy.memory(1)); action('M3', () => easy.memory(2));
    action('EXIT_SAVE', () => easy.save(easy.selectedSeat));
    action('EXIT_MOVE', () => easy.move(easy.selectedSeat));
    action('MAKE_ROOM', () => easy.makeRoom());
    action('STOP', () => easy.stop());
    easy.on('change', draw);

    function foreground() {
        easy.setForeground(visible && focused);
        if (easy.foreground && !easy.pending) easy.refresh().catch(() => {});
    }
    main = comp('MAIN');
    if (main) {
        main.on('visible', (event) => { visible = !!(event && event.visible); if (!visible) focused = false; foreground(); });
        main.on('focus', (event) => { focused = !!(event && event.focus === true); foreground(); });
    }
    rhmi.on('applicationStackChanged', (stack) => {
        const shown = !!stack && Object.prototype.hasOwnProperty.call(stack, 'ROOT_APP');
        Promise.resolve(shown ? app.registerHmiVisible() : app.unregisterHmiVisible()).catch(() => {});
    });
    const description = opts.description || require('../rhmiData/application.json');
    const entries = description.application.entryPoints.map((entry) => entry.uuid);
    async function open(uuid) {
        if (!uuid || !main) return;
        await bounded(rhmi.mapEntryState(uuid, main), 3000, 'entry mapping timeout');
        if (main.updateResources) await bounded(main.updateResources(), 3000, 'resource timeout');
        await bounded(rhmi.openEntryState(uuid), 3000, 'entry opening timeout');
    }
    app.on('entryPointExecute', (uuid) => open(uuid).catch(() => {}));
    await Promise.all(entries.map((id) => rhmi.mapEntryState(id, main))).catch(() => {});
    if (main && main.updateResources) await main.updateResources().catch(() => {});
    draw(); await app.initialized();
    const last = app.getLastExecutedEntryPointUuid && app.getLastExecutedEntryPointUuid();
    if (last && ['ENTRY_POINT', 'BOOKMARK', 'LUM'].indexOf(String(app.startReason)) >= 0) open(last).catch(() => {});
    timer = setInterval(() => draw(), 1000);
    return { app: app, easy: easy, close: close, version: VERSION };
}
module.exports = { run };

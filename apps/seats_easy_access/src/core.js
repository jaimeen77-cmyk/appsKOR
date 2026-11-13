'use strict';

// Independent client for the public iteriodev-comfort JSON-lines protocol.
const EventEmitter = require('events');
const net = require('net');
const SOCKET = '/run/iteriodev-comfort/ctl.sock';
const VERSION = '0.3.2';

function bounded(promise, ms, message) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error(message || 'timeout')), ms);
        Promise.resolve(promise).then((value) => { clearTimeout(timer); resolve(value); },
            (error) => { clearTimeout(timer); reject(error); });
    });
}

function stateOf(message) {
    const state = message && message.state;
    const seats = state && state.seats;
    if (!state || !seats || !seats.axes || !seats.pos) return null;
    const clean = {
        parked: state.parked === true,
        carOn: state.carOn === true,
        settings: { easyExit: !!(state.settings && state.settings.easyExit) },
        seats: {
            axes: { driver: [], passenger: [] }, pos: { driver: {}, passenger: {} },
            exit: { driver: !!(seats.exit && seats.exit.driver), passenger: !!(seats.exit && seats.exit.passenger) },
            pre: { driver: !!(seats.pre && seats.pre.driver), passenger: !!(seats.pre && seats.pre.passenger) },
            moving: seats.moving && typeof seats.moving === 'object' ? {
                seat: seats.moving.seat === 'passenger' ? 'passenger' : 'driver',
                axis: typeof seats.moving.axis === 'string' ? seats.moving.axis : null,
            } : null,
            job: seats.job === null ? null : (typeof seats.job === 'string' ? seats.job : 'busy'),
            jobSeat: seats.jobSeat === 'driver' || seats.jobSeat === 'passenger' ? seats.jobSeat : null,
            wheel: seats.wheel === true,
            roomOut: seats.roomOut === true,
        },
    };
    ['driver', 'passenger'].forEach((who) => {
        const axes = Array.isArray(seats.axes[who]) ? seats.axes[who] : [];
        clean.seats.axes[who] = axes.filter((axis) => typeof axis === 'string' && /^[A-Z]{3}$/.test(axis));
        clean.seats.axes[who].forEach((axis) => {
            const value = seats.pos[who] && seats.pos[who][axis];
            if (typeof value === 'number' && isFinite(value)) clean.seats.pos[who][axis] = value;
        });
    });
    return clean;
}

function validCommand(message) {
    if (!message || typeof message !== 'object') return false;
    if ((message.op === 'get' || message.op === 'stop' || message.op === 'gentleman') && Object.keys(message).length === 1) return true;
    if (message.op === 'exit' && (message.seat === 'driver' || message.seat === 'passenger') &&
        typeof message.save === 'boolean' && Object.keys(message).length === 3) return true;
    if (message.op === 'jog' && (message.seat === 'driver' || message.seat === 'passenger') &&
        /^(SLV|SHV|LNV|SNV|KHV)$/.test(message.axis) && (message.dir === 1 || message.dir === -1) &&
        Object.keys(message).length === 4) return true;
    if (message.op === 'memory' && (message.seat === 'driver' || message.seat === 'passenger') &&
        [0, 1, 2].indexOf(message.slot) >= 0 && typeof message.save === 'boolean' &&
        Object.keys(message).length === 4) return true;
    return message.op === 'set' && message.settings && typeof message.settings.easyExit === 'boolean' &&
        Object.keys(message).length === 2 && Object.keys(message.settings).length === 1;
}

class ComfortClient extends EventEmitter {
    constructor(socketPath) {
        super(); this.path = socketPath || SOCKET; this.socket = null; this.connecting = null;
        this.state = null; this.at = 0;
    }
    async connect() {
        if (this.socket && !this.socket.destroyed) return;
        if (this.connecting) return this.connecting;
        this.connecting = new Promise((resolve, reject) => {
            let buffer = '', connected = false;
            const socket = net.createConnection(this.path);
            const timer = setTimeout(() => socket.destroy(new Error('Comfort connection timeout')), 1500);
            socket.setEncoding('utf8');
            socket.on('connect', () => { connected = true; clearTimeout(timer); this.socket = socket; resolve(); });
            socket.on('data', (chunk) => {
                buffer += chunk;
                if (buffer.length > 65536) return socket.destroy(new Error('Oversized Comfort response'));
                let newline;
                while ((newline = buffer.indexOf('\n')) >= 0) {
                    const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1);
                    let packet;
                    try { packet = JSON.parse(line); } catch (_) { continue; }
                    const state = stateOf(packet);
                    if (state) { this.state = state; this.at = Date.now(); this.emit('state', state); }
                }
            });
            socket.on('error', (error) => { if (!connected) reject(error); this.emit('clientError', error); });
            socket.on('close', () => {
                clearTimeout(timer);
                if (!connected) reject(new Error('Comfort disconnected before connection'));
                if (this.socket === socket) this.socket = null;
                this.state = null; this.at = 0; this.emit('lost');
            });
        });
        try { await this.connecting; } finally { this.connecting = null; }
    }
    send(message) {
        if (!validCommand(message)) return Promise.reject(new Error('Command outside Easy Access scope'));
        if (!this.socket || this.socket.destroyed) return Promise.reject(new Error('Comfort is not connected'));
        return bounded(new Promise((resolve, reject) => {
            this.socket.write(JSON.stringify(message) + '\n', (error) => error ? reject(error) : resolve());
        }), 700, 'Comfort write timeout');
    }
    async refresh() {
        await this.connect();
        return new Promise((resolve, reject) => {
            const done = (error, value) => {
                clearTimeout(timer); this.removeListener('state', gotState); this.removeListener('lost', lost);
                error ? reject(error) : resolve(value);
            };
            const gotState = (value) => done(null, value);
            const lost = () => done(new Error('Comfort disconnected'));
            const timer = setTimeout(() => done(new Error('No valid Comfort status')), 1800);
            this.once('state', gotState); this.once('lost', lost);
            this.send({ op: 'get' }).catch((error) => done(error));
        });
    }
    close() { if (this.socket) this.socket.destroy(); }
}

class EasyAccess extends EventEmitter {
    constructor(client) {
        super(); this.client = client; this.foreground = false; this.pending = false; this.moving = false;
        this.selectedSeat = 'driver'; this.saveMemory = false; this.message = '상태를 확인하세요.';
        client.on('state', () => this.emit('change'));
        client.on('lost', () => { this.message = 'Comfort 연결이 끊겼습니다.'; this.emit('change'); });
    }
    setForeground(on) { this.foreground = !!on; this.emit('change'); }
    state() { return this.client.state; }
    selectSeat(who) {
        if (who !== 'driver' && who !== 'passenger') throw new Error('지원하지 않는 시트입니다.');
        if (this.pending || this.moving) throw new Error('시트 요청이 끝난 뒤 좌석을 변경하세요.');
        this.selectedSeat = who; this.saveMemory = false;
        this.message = who === 'driver' ? '운전석을 선택했습니다.' : '조수석을 선택했습니다.';
        this.emit('change');
    }
    seatReady(who) {
        const state = this.state();
        if (!state) return 'Comfort 상태를 먼저 확인하세요.';
        if (!state.seats.axes[who].length) return (who === 'driver' ? '운전석' : '조수석') + ' 조절 축을 찾지 못했습니다.';
        if (!Object.keys(state.seats.pos[who]).length) return '위치 센서가 없는 시트에서는 Easy Access를 저장할 수 없습니다.';
        return null;
    }
    actionReady(who, requireParked) {
        if (!this.foreground) return '앱 화면이 활성화되어 있어야 합니다.';
        if (this.pending) return '이전 요청을 처리하는 중입니다.';
        const seat = this.seatReady(who);
        if (seat) return seat;
        const state = this.state();
        if (state.seats.moving || state.seats.job) return '시트가 움직이는 중입니다. 먼저 정지하세요.';
        if (requireParked && !state.parked) return '정차 상태에서만 사용할 수 있습니다.';
        return null;
    }
    async refresh() {
        this.pending = true; this.message = '상태 확인 중…'; this.emit('change');
        try { await this.client.refresh(); this.message = 'Easy Access 상태를 확인했습니다.'; }
        catch (error) { this.message = '상태 확인 실패: ' + error.message; throw error; }
        finally { this.pending = false; this.emit('change'); }
    }
    async request(message, success) {
        this.pending = true; this.message = '요청 전송 중…'; this.emit('change');
        try { await this.client.send(message); await this.client.refresh(); this.message = success; }
        catch (error) { this.message = '요청 실패: ' + error.message; throw error; }
        finally { this.pending = false; this.emit('change'); }
    }
    async toggle() {
        const state = this.state();
        if (!this.foreground || !state) throw new Error('상태 확인 후 앱 화면에서 변경하세요.');
        return this.request({ op: 'set', settings: { easyExit: !state.settings.easyExit } },
            !state.settings.easyExit ? 'Easy Access 자동 작동을 켰습니다.' : 'Easy Access 자동 작동을 껐습니다.');
    }
    async save(who) {
        const blocked = this.actionReady(who, true); if (blocked) throw new Error(blocked);
        return this.request({ op: 'exit', seat: who, save: true },
            (who === 'driver' ? '운전석' : '조수석') + ' 하차 위치를 저장했습니다.');
    }
    async move(who) {
        const blocked = this.actionReady(who, true); if (blocked) throw new Error(blocked);
        return this.request({ op: 'exit', seat: who, save: false },
            (who === 'driver' ? '운전석' : '조수석') + ' Easy Access 이동을 요청했습니다.');
    }
    async makeRoom() {
        const blocked = this.actionReady('passenger', true);
        if (blocked) throw new Error(blocked);
        if (this.selectedSeat !== 'passenger') throw new Error('조수석 탭에서 사용하세요.');
        await this.client.refresh();
        const recheck = this.actionReady('passenger', true);
        if (recheck) throw new Error(recheck);
        const returning = this.state().seats.roomOut;
        return this.request({ op: 'gentleman' }, returning ?
            '조수석 원위치 복귀를 요청했습니다.' : '조수석 공간 확보를 요청했습니다.');
    }
    async jog(axis, direction) {
        const who = this.selectedSeat;
        const blocked = this.actionReady(who, false); if (blocked) throw new Error(blocked);
        const state = this.state();
        if (state.seats.axes[who].indexOf(axis) < 0) throw new Error('이 시트가 지원하지 않는 조절 축입니다.');
        this.pending = true; this.moving = true; this.message = '시트 이동 중…'; this.emit('change');
        let moveError = null;
        try { await this.client.send({ op: 'jog', seat: who, axis: axis, dir: direction }); }
        catch (error) { moveError = error; }
        await new Promise((resolve) => setTimeout(resolve, 250));
        try { await this.client.send({ op: 'stop' }); }
        catch (error) { if (!moveError) moveError = error; }
        this.pending = false; this.moving = false;
        if (moveError) { this.message = '이동 실패: ' + moveError.message; this.emit('change'); throw moveError; }
        this.message = '짧은 이동을 완료했습니다.'; this.emit('change');
    }
    armMemorySave() {
        if (!this.foreground) throw new Error('앱 화면이 활성화되어 있어야 합니다.');
        this.saveMemory = !this.saveMemory;
        this.message = this.saveMemory ? '저장할 M1~M3 버튼을 누르세요.' : '메모리 저장을 취소했습니다.';
        this.emit('change');
    }
    async memory(slot) {
        const who = this.selectedSeat;
        const blocked = this.actionReady(who, true); if (blocked) throw new Error(blocked);
        const save = this.saveMemory; this.saveMemory = false;
        return this.request({ op: 'memory', seat: who, slot: slot, save: save },
            (who === 'driver' ? '운전석' : '조수석') + ' M' + (slot + 1) + (save ? '에 저장했습니다.' : ' 호출을 요청했습니다.'));
    }
    async stop() {
        if (!this.foreground) throw new Error('앱 화면이 활성화되어 있어야 합니다.');
        return this.request({ op: 'stop' }, '정지를 요청했습니다. 실제로 멈췄는지 확인하세요.');
    }
}

module.exports = { ComfortClient, EasyAccess, stateOf, validCommand, bounded, VERSION, SOCKET };

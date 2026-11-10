'use strict';
/* wanted.json is Cluster Info's: these apps write it only when no other app has one, and remove theirs as soon
 * as they stop wanting (a leftover of ours in the sticky folder stopped eDrive Live sharing with Cluster Info).
 * Each also asks in its own wanted-<id>.json (a stale wanted.json of Cluster Info's stopped eDrive Live sharing with
 * them). */
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { startProviders } = require(path.join(__dirname, '..', 'shared', 'providers'));

const log = { info() {}, warn() {} };
let ok = 0;
const check = (name, fn) => { fn(); ok++; console.log('ok   ' + name); };
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ci-'));
const W = path.join(dir, 'wanted.json');
const realUid = process.getuid;

check('wants: writes wanted.json; release removes it', () => {
    const p = startProviders(log, { dir, scanMs: 60000 });
    p.want({ power: true });
    assert(fs.existsSync(W) && JSON.parse(fs.readFileSync(W, 'utf8')).power === true);
    p.release();
    assert(!fs.existsSync(W));
    p.stop();
});

check('another app\'s stale wanted.json (Cluster Info\'s, left behind) is left alone, and this app still asks in its own file', () => {
    fs.writeFileSync(W, JSON.stringify({ t: 1, from: 'cluster info' }));
    process.getuid = () => realUid() + 1;   // this app runs as another uid than the file's owner
    try {
        const p = startProviders(log, { dir, scanMs: 60000 });
        p.want({ power: true });
        const own = fs.readdirSync(dir).filter((n) => /^wanted-.+\.json$/.test(n));
        assert.strictEqual(own.length, 1, 'its own wanted file');
        const w = JSON.parse(fs.readFileSync(path.join(dir, own[0]), 'utf8'));
        assert(w.power === true && Date.now() - w.t < 3000);
        assert.deepStrictEqual(Object.keys(p.readings()).filter((k) => p.readings()[k] !== undefined), [], 'a wanted file is not a provider');
        p.release();
        p.stop();
        assert(!fs.readdirSync(dir).some((n) => /^wanted-/.test(n)), 'its own removed on release');
        assert.strictEqual(JSON.parse(fs.readFileSync(W, 'utf8')).from, 'cluster info');
    } finally { process.getuid = realUid; }
    fs.unlinkSync(W);
});

check('eDrive Live\'s power: its last reading held through a missed read (old), and the battery left to it', () => {
    const f = path.join(dir, 'edrive2.json');
    fs.writeFileSync(f, JSON.stringify({ v: 1, t: Date.now(), app: 'eDrive Live', power: { kw: 23.5, old: true }, values: {} }));
    const p = startProviders(log, { dir, scanMs: 60000, watch: false });
    try {
        assert.strictEqual(p.readings().kw, 23.5);
        assert.strictEqual(p.powerShared(), true);
    } finally { p.stop(); fs.unlinkSync(f); }
});

check('a leftover of ours is removed at start', () => {
    fs.writeFileSync(W, JSON.stringify({ t: 1 }));
    const p = startProviders(log, { dir, scanMs: 60000 });
    assert(!fs.existsSync(W));
    p.stop();
});

fs.rmSync(dir, { recursive: true, force: true });
console.log(ok + ' passed');

'use strict';
// RHMI Text is not a reliable Unicode transport on this firmware. Use the SDK's
// UTF-8 StringBundle and StringId handles for non-ASCII values instead.
// A component without a usable string bundle (seen with Korean on iDrive 8: the app's start
// failed there, so its tile stayed on "Loading") or a bundle that refuses the strings gets
// the text as plain Text instead: never a throw that stops the app's start.
const { t } = require('./i18n');
const SLOT_COUNT = 256; // HMI accepts at most 1024 strings, including all static menu resources.
const slotId = (n) => 'SID_CN_DYNAMIC_' + ('0000' + n).slice(-4);
let warned = false;
function warnOnce(why) {
    if (warned) return;
    warned = true;
    try { require('./mgu').log.warn('HMI string bundle ' + why + ': non-ASCII text goes as plain Text'); } catch (e) { /* no log */ }
}
class HmiText {
    constructor() { this.slots = new Map(); }
    set(component, name, row, cell, value) {
        const key = JSON.stringify([name, row, cell]);
        const text = t(value);
        const plain = () => component.setValue(row, cell, text, 'Text');
        if (!/[^\x20-\x7e]/.test(text)) return plain();
        let bundle = null;
        try { bundle = typeof component.getStringBundle === 'function' ? component.getStringBundle() : null; } catch (e) { bundle = null; }
        if (!bundle || typeof bundle.setStrings !== 'function') { warnOnce('not available'); return plain(); }
        if (!this.slots.has(key)) {
            if (this.slots.size >= SLOT_COUNT) return Promise.reject(new Error('Chinese text resource pool exhausted'));
            this.slots.set(key, slotId(this.slots.size));
        }
        const sid = this.slots.get(key);
        const strings = {}; strings[sid] = text;
        return Promise.resolve().then(() => bundle.setStrings(strings))
            .then(() => component.setValue(row, cell, sid, 'StringId'), (e) => { warnOnce('refused (' + e + ')'); return plain(); });
    }
}
module.exports = { HmiText, SLOT_COUNT, slotId };

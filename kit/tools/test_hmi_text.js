'use strict';
// hmi-text.js: non-ASCII text goes through the component's string bundle; without a usable bundle
// (iDrive 8: Korean apps' start failed there and the tile stayed on "Loading") or when the bundle
// refuses, it goes as plain Text, and set() never throws.
//   node kit/tools/test_hmi_text.js
const assert = require('assert');
const path = require('path');
const { HmiText, slotId } = require(path.join(__dirname, '..', 'runtime', 'hmi-text'));

(async () => {
    const run = async (component) => {
        const writes = [];
        component.setValue = async (...a) => writes.push(a);
        let r;
        assert.doesNotThrow(() => { r = new HmiText().set(component, 'ROW', 0, 'FrequencyText', '켜짐'); });
        await r;
        return writes;
    };
    let bundled = [];
    assert.deepStrictEqual(await run({ getStringBundle: () => ({ setStrings: async (s) => bundled.push(s) }) }),
        [[0, 'FrequencyText', slotId(0), 'StringId']]);
    assert.deepStrictEqual(bundled, [{ [slotId(0)]: '켜짐' }]);
    const plain = [[0, 'FrequencyText', '켜짐', 'Text']];
    assert.deepStrictEqual(await run({}), plain, 'no getStringBundle');
    assert.deepStrictEqual(await run({ getStringBundle: () => undefined }), plain, 'no bundle');
    assert.deepStrictEqual(await run({ getStringBundle: () => { throw new Error('x'); } }), plain, 'bundle throws');
    assert.deepStrictEqual(await run({ getStringBundle: () => ({}) }), plain, 'bundle without setStrings');
    assert.deepStrictEqual(await run({ getStringBundle: () => ({ setStrings: () => Promise.reject(new Error('no')) }) }), plain, 'bundle refuses');
    assert.deepStrictEqual(await run({ getStringBundle: () => ({ setStrings: () => { throw new Error('no'); } }) }), plain, 'setStrings throws');
    assert.deepStrictEqual(await run({}).then(() => run({ getStringBundle() { throw 0; } })), plain);
    const ascii = []; await new HmiText().set({ setValue: async (...a) => ascii.push(a) }, 'ROW', 0, 'Text', 'On');
    assert.deepStrictEqual(ascii, [[0, 'Text', 'On', 'Text']]);
    console.log('PASS: hmi-text string bundle, and plain Text without a usable bundle (iDrive 8)');
})().catch((e) => { console.error(e); process.exit(1); });

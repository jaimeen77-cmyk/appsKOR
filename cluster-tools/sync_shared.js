'use strict';
/**
 * sync_shared.js - copies shared/ (the cluster engine, shaders, glyph atlases, render client, car data,
 * providers, signal finder, the signed credit) into the apps that use it. The build ships only an app's own
 * top-level files, so each app carries its copy; edit shared/, then run this. test_shared.js fails while a copy
 * differs. An app takes shared files only when its app.json asks: "shared": true (all of them) or a list of
 * names. Apps without it (Cluster Info, with its own providers and render client) are never touched.
 *   node tools/sync_shared.js
 */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..'), SHARED = path.join(ROOT, 'shared'), APPS = path.join(ROOT, 'apps');
const files = () => fs.readdirSync(SHARED).filter((f) => f.endsWith('.js') || /^font_\w+\.wad$/.test(f) || f === 'NOTICE');
/** The shared files an app takes: all with "shared": true, the named ones with a list, none without. */
const filesFor = (a) => {
    let j = {};
    try { j = JSON.parse(fs.readFileSync(path.join(APPS, a, 'app.json'), 'utf8')); } catch (e) { /* none */ }
    if (j.shared === true) return files();
    return Array.isArray(j.shared) ? files().filter((f) => j.shared.indexOf(f) >= 0) : [];
};
const apps = () => fs.readdirSync(APPS).filter((a) => fs.existsSync(path.join(APPS, a, 'app.json')) && filesFor(a).length > 0);
/** [{ app, file, same }] for every shared file in every app. */
function compare() {
    const out = [];
    apps().forEach((a) => filesFor(a).forEach((f) => {
        const dst = path.join(APPS, a, f);
        out.push({ app: a, file: f, same: fs.existsSync(dst) && fs.readFileSync(dst).equals(fs.readFileSync(path.join(SHARED, f))) });
    }));
    return out;
}
if (require.main === module) {
    apps().forEach((a) => filesFor(a).forEach((f) => fs.copyFileSync(path.join(SHARED, f), path.join(APPS, a, f))));
    console.log('shared: ' + apps().map((a) => a + ' ' + filesFor(a).length).join(', '));
}
module.exports = { compare };

#!/usr/bin/env python3
"""Validate Korean compiled layers, source freshness and Store package assembly."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def car_build(prepare, component, listing, files):
    """The Store's build on a head unit: only the entry's path and "shared" files, the unit's oap-sdk
    (a stand-in here) at the root. The package is the checked layer plus that oap-sdk and the
    home-screen widget the preview build stops before."""
    app = component['id']
    with tempfile.TemporaryDirectory(prefix='korean-store-car-') as work:
        tree = Path(work) / 'repo'
        for rel in [component['path']] + component['build']['shared']:
            source, dest = ROOT / rel, tree / rel
            if rel == 'oap-sdk':
                dest.mkdir(parents=True)
                (dest / 'index.js').write_text('module.exports = {};\n')
                (dest / 'package.json').write_text('{"name": "oap-sdk", "version": "0.0.0-test"}\n')
            elif source.is_dir():
                shutil.copytree(source, dest, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.wad'))
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
        env = dict(os.environ, MGU_OUT=str(Path(work) / 'out'))
        env.pop('MGU_SOMEIP_CATALOG', None)
        subprocess.run([sys.executable, str(tree / component['build']['python'])] +
                       [a.format(id=app, version=listing['version'], dir=component['path'])
                        for a in component['build']['args']],
                       cwd=str(tree), env=env, check=True, stdout=subprocess.DEVNULL)
        with tarfile.open(str(Path(work) / 'out' / (app + '@' + listing['version'] + '.tgz'))) as archive:
            built = {n: archive.extractfile(n).read() for n in archive.getnames() if archive.getmember(n).isfile()}
    extra = set(built) - set(files)
    assert set(files) <= set(built), app + ': head-unit build lacks ' + repr(sorted(set(files) - set(built))[:5])
    assert {'package/node_modules/oap-sdk/index.js', 'package/node_modules/oap-sdk/package.json'} <= extra
    assert all(n.startswith(('package/node_modules/oap-sdk/', 'package/rhmiDataStartWidget/')) for n in extra), sorted(extra)
    assert all(built[n] == b for n, b in files.items()), app + ': head-unit build differs from the checked layer'


def check(build=False, car=False):
    prepare = module('prepare', 'prepare-korean-store.py')
    installer = module('installer', 'install-korean.py')
    repo = json.loads((ROOT / 'mgu-repo.json').read_text())
    assert 'apps' not in repo
    components = [c for c in repo['components'] if c['path'].startswith('store/apps/')]
    expected = {p.parent.name for p in (ROOT / 'apps').glob('*/app.json')}
    assert {c['id'] for c in components} == expected and len(components) == len(expected)
    results = []
    for component in components:
        app = component['id']
        listing = json.loads((ROOT / component['path'] / 'app.json').read_text())
        source = json.loads((ROOT / 'apps' / app / 'app.json').read_text())
        own, delta = installer.read_layer(ROOT / 'store/korean' / app)
        common, shared = installer.read_common(own)
        assert listing['version'] == own['version']
        assert own['common_sha256'] == common['sha256']
        # Built on the head unit with its oap-sdk, as appsKOR_fork's own Store entry is.
        assert component['build'] == prepare.car_build(app), app + ': Store build is not the head-unit build'
        assert set(shared).isdisjoint(delta)
        files = dict(shared, **delta)
        assert all('node_modules' not in n.split('/') and 'oap-sdk' not in n.split('/') for n in files)
        assert json.loads(files['package/javascript/kit/locale.json'])['language'] == 'ko'
        pkg = json.loads(files['package/package.json'])
        assert pkg['name'] == app and pkg['version'] == listing['version'] and pkg['mguLocalOnly']
        # iDrive 7 / 8: the source app.json (appsKOR_fork) decides; the listing and the package say the same.
        hmi = prepare.hmi_of(source)
        assert component['mguHmi'] == hmi, '%s: mgu-repo.json mguHmi %r, apps/%s/app.json %r' % (app, component['mguHmi'], app, hmi)
        assert pkg['mguHmi'] == hmi, '%s: package mguHmi %r, apps/%s/app.json %r; regenerate with tools/prepare-korean-store.py' % (app, pkg['mguHmi'], app, hmi)
        spec = json.loads(files['package/javascript/kit/app-spec.json'])
        # versions and code exactly as the source (appsKOR_fork)
        assert listing['version'] == source['version']
        assert own['source_hash'] == prepare.inputs(app), 'Korean compiled app is stale: ' + app
        assert files['package/javascript/kit/fonts/korean.json'] == (ROOT / 'kit/localization/fonts/korean.json').read_bytes()
        assert files['package/javascript/app.js'] == (ROOT / 'apps' / app / 'main.js').read_bytes()
        for old, new in zip(source['settings'], spec['settings']):
            assert old['key'] == new['key'] and old['default'] == new['default']
            assert [o[0] for o in old.get('options', [])] == [o[0] for o in new.get('options', [])]
        if app == 'doom':
            assert hashlib.sha256(files['package/javascript/freedoom1.wad']).hexdigest() == source['assets'][0]['sha256']
        if build:
            with tempfile.TemporaryDirectory(prefix='korean-store-check-') as work:
                target = installer.assemble(app, listing['version'], component['path'], Path(work) / 'out')
                with tarfile.open(target) as archive:
                    assert set(archive.getnames()) == set(files)
                    assert all(archive.extractfile(n).read() == b for n, b in files.items())
        if car:
            car_build(prepare, component, listing, files)
        results.append(app)
    # Host tests exercise a Store ID collision using a temporary manifest. Keep
    # it inside the repo, where the same path guards apply on the car.
    temporary = ROOT / 'store/apps/service_kor_test'
    if temporary.exists():
        raise ValueError('Test alias folder already exists')
    try:
        temporary.mkdir()
        listing = json.loads((ROOT / 'store/apps/service/app.json').read_text())
        listing['id'] = 'service_kor_test'
        (temporary / 'app.json').write_text(json.dumps(listing))
        with tempfile.TemporaryDirectory(prefix='korean-store-alias-') as work:
            target = installer.assemble(listing['id'], listing['version'], str(temporary.relative_to(ROOT)), Path(work) / 'out')
            with tarfile.open(target) as archive:
                pkg = json.load(archive.extractfile('package/package.json'))
                app = json.load(archive.extractfile('package/rhmiData/application.json'))['application']
                assert pkg['name'] == app['name'] == listing['id']
                own, delta = installer.read_layer(ROOT / 'store/korean/service')
                _, shared = installer.read_common(own)
                expected_files = dict(shared, **delta)
                assert json.load(archive.extractfile('package/manifest.json')) == json.loads(expected_files['package/manifest.json']), 'Alias must not rewrite service keys or signal interfaces'
                for entry in app['entryPoints']:
                    assert 'package/rhmiData/variantGroups/Common/images/' + entry['icon'] in archive.getnames()
    finally:
        shutil.rmtree(temporary)
    for invalid in ['../common', 'bad', '0' * 64]:
        try:
            installer.read_common({'common_sha256': invalid})
        except ValueError:
            pass
        else:
            raise AssertionError('Unknown or unsafe common layer accepted')
    print('PASS: %d Korean compiled apps; source versions, local source freshness, exact package bytes, matching runtime cohorts, fonts, Doom data and Store collision IDs.' % len(results))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='assemble and inspect all installable SDK-free archives')
    parser.add_argument('--car', action='store_true', help="also build every app as the Store does on a head unit (stand-in oap-sdk)")
    args = parser.parse_args()
    check(args.build, args.car)

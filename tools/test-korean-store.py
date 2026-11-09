#!/usr/bin/env python3
"""Validate Korean compiled layers, source freshness and Store package assembly."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def check(build=False):
    prepare = module('prepare', 'prepare-korean-store.py')
    installer = module('installer', 'install-korean.py')
    repo = json.loads((ROOT / 'mgu-repo.json').read_text())
    assert 'apps' not in repo
    components = repo['components']
    expected = {p.parent.name for p in (ROOT / 'apps').glob('*/app.json')}
    assert {c['id'] for c in components} == expected and len(components) == len(expected)
    common, shared = installer.read_layer(ROOT / 'store/korean/common')
    results = []
    for component in components:
        app = component['id']
        listing = json.loads((ROOT / component['path'] / 'app.json').read_text())
        source = json.loads((ROOT / 'apps' / app / 'app.json').read_text())
        own, delta = installer.read_layer(ROOT / 'store/korean' / app)
        assert listing['version'] == source['version'] == own['version']
        assert own['source_hash'] == prepare.inputs(app), 'Korean compiled app is stale: ' + app
        assert own['common_sha256'] == common['sha256']
        assert component['build']['network'] is False and 'sdk' not in component['build']
        assert set(shared).isdisjoint(delta)
        files = dict(shared, **delta)
        assert all('node_modules' not in n.split('/') and 'oap-sdk' not in n.split('/') for n in files)
        assert json.loads(files['package/javascript/kit/locale.json'])['language'] == 'ko'
        pkg = json.loads(files['package/package.json'])
        assert pkg['name'] == app and pkg['version'] == source['version'] and pkg['mguLocalOnly']
        assert files['package/javascript/kit/fonts/korean.json'] == (ROOT / 'kit/localization/fonts/korean.json').read_bytes()
        assert files['package/javascript/app.js'] == (ROOT / 'apps' / app / 'main.js').read_bytes()
        spec = json.loads(files['package/javascript/kit/app-spec.json'])
        for old, new in zip(source['settings'], spec['settings']):
            assert old['key'] == new['key'] and old['default'] == new['default']
            assert [o[0] for o in old.get('options', [])] == [o[0] for o in new.get('options', [])]
        if app == 'doom':
            assert hashlib.sha256(files['package/javascript/freedoom1.wad']).hexdigest() == source['assets'][0]['sha256']
        if build:
            with tempfile.TemporaryDirectory(prefix='korean-store-check-') as work:
                target = installer.assemble(app, source['version'], component['path'], Path(work) / 'out')
                with tarfile.open(target) as archive:
                    assert set(archive.getnames()) == set(files)
                    assert all(archive.extractfile(n).read() == b for n, b in files.items())
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
                expected_files = dict(shared, **delta)
                assert json.load(archive.extractfile('package/manifest.json')) == json.loads(expected_files['package/manifest.json']), 'Alias must not rewrite service keys or signal interfaces'
                for entry in app['entryPoints']:
                    assert 'package/rhmiData/variantGroups/Common/images/' + entry['icon'] in archive.getnames()
    finally:
        shutil.rmtree(temporary)
    print('PASS: %d Korean compiled apps; source freshness, checksums, unchanged settings, fonts, Doom data and Store collision IDs.' % len(results))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='assemble and inspect all installable SDK-free archives')
    check(parser.parse_args().build)

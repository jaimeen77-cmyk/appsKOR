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
    # Each import pins the packages it published; a later import replaces an
    # earlier one's pins for the same app.
    imported = {}
    for record in sorted((ROOT / 'store/migrations').glob('apps-*.json')):
        imported.update(json.loads(record.read_text())['apps'])
    results = []
    for component in components:
        app = component['id']
        listing = json.loads((ROOT / component['path'] / 'app.json').read_text())
        source = json.loads((ROOT / 'apps' / app / 'app.json').read_text())
        own, delta = installer.read_layer(ROOT / 'store/korean' / app)
        common, shared = installer.read_common(own)
        assert listing['version'] == own['version']
        assert own['common_sha256'] == common['sha256']
        assert component['build']['network'] is False and 'sdk' not in component['build']
        assert set(shared).isdisjoint(delta)
        files = dict(shared, **delta)
        assert all('node_modules' not in n.split('/') and 'oap-sdk' not in n.split('/') for n in files)
        assert json.loads(files['package/javascript/kit/locale.json'])['language'] == 'ko'
        pkg = json.loads(files['package/package.json'])
        assert pkg['name'] == app and pkg['version'] == listing['version'] and pkg['mguLocalOnly']
        spec = json.loads(files['package/javascript/kit/app-spec.json'])
        pin = imported.get(app)
        if pin and own.get('source_commit') == pin['source_commit'] and own.get('source_hash') == pin['source_hash']:
            # These packages were built from a newer pinned source than this
            # repo's retained source checkout. Verify every published byte
            # against the migration inventory, rather than relabeling old code.
            pairs = sorted((name, hashlib.sha256(data).hexdigest()) for name, data in files.items())
            digest = hashlib.sha256(json.dumps(pairs, separators=(',', ':')).encode()).hexdigest()
            assert listing['version'] == pin['version']
            assert own['sha256'] == pin['layer_sha256'] and own['common_sha256'] == pin['common_sha256']
            assert digest == pin['package_contents_sha256'], 'Imported package changed: ' + app
        else:
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
    print('PASS: %d Korean compiled apps; pinned imports, local source freshness, exact package bytes, matching runtime cohorts, fonts, Doom data and Store collision IDs.' % len(results))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='assemble and inspect all installable SDK-free archives')
    check(parser.parse_args().build)

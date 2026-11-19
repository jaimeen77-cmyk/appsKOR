#!/usr/bin/env python3
"""Build a Korean Store app on the head unit, the way appsKOR_fork's Store entry does.

The MGU Store runs this on the car with "sdk": "oap-sdk": it puts the oap-sdk module it
made from this unit's own donor at <repo>/oap-sdk. kit/tools/build.py then builds the
original apps/<sourceId> in Korean with that SDK in node_modules/oap-sdk and fits the
SOME/IP manifest to this unit's interface catalog (iDrive 7 or iDrive 8). Packages
prebuilt without either stayed on "Loading" on iDrive 8.

The SDK is never in this repository; this script does not copy it anywhere but into
the package it writes to MGU_OUT.
"""
import argparse
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 128 * 1024 * 1024


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load('install_korean', ROOT / 'tools' / 'install-korean.py')
store = load('prepare_korean_store', ROOT / 'tools' / 'prepare-korean-store.py')


def read_package(path):
    with gzip.open(str(path), 'rb') as compressed:
        raw = compressed.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('Built package exceeds the unpacked limit')
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        for member in archive:
            if member.isdir():
                continue
            parts = PurePosixPath(member.name).parts
            if (not member.isfile() or not parts or parts[0] != 'package' or '..' in parts or
                    '\\' in member.name or member.name in files):
                raise ValueError('Unexpected built member: ' + member.name)
            files[member.name] = archive.extractfile(member).read()
    return files


def build(app_id, version, directory, output):
    if not installer.ID.fullmatch(app_id) or not installer.VERSION.fullmatch(version):
        raise ValueError('Invalid app identity/version')
    directory = installer.inside(ROOT / directory)
    listing = json.loads((directory / 'app.json').read_text(encoding='utf-8'))
    original = listing.get('sourceId')
    if (not isinstance(original, str) or not installer.ID.fullmatch(original) or
            listing['id'] != app_id or listing['version'] != version):
        raise ValueError('Store listing does not match requested package')
    source = json.loads((ROOT / 'apps' / original / 'app.json').read_text(encoding='utf-8'))
    if source.get('version') != version:
        raise ValueError('Store listing %s does not match apps/%s/app.json %s' % (version, original, source.get('version')))
    sdk = ROOT / 'oap-sdk'
    if not ((sdk / 'index.js').is_file() and (sdk / 'package.json').is_file()):
        raise SystemExit("The Store did not provide the head unit's oap-sdk (\"sdk\": \"oap-sdk\")")

    sys.path.insert(0, str(ROOT / 'kit' / 'tools'))
    kit = load('kit_build', ROOT / 'kit' / 'tools' / 'build.py')
    compiled = kit.localize_spec(json.loads(json.dumps(source)), 'ko')['version']
    package = ROOT / 'dist' / (original + '@' + compiled + '.tgz')
    if package.exists():
        package.unlink()
    kit.build(original, 'ko')

    # The same identity as the prebuilt layers: x.y.z for the Store, the source mguHmi.
    files = store.store_identity(read_package(package), original, source, compiled)
    pkg = json.loads(files['package/package.json'].decode('utf-8'))
    locale = json.loads(files['package/javascript/kit/locale.json'].decode('utf-8'))
    if (pkg['name'] != original or pkg['version'] != version or locale['language'] != 'ko' or
            pkg.get('mguHmi') != store.hmi_of(source)):
        raise ValueError('Built identity/language/mguHmi mismatch')
    for name in ('package/javascript/app.js', 'package/javascript/kit/fonts/korean.json',
                 'package/node_modules/oap-sdk/index.js', 'package/node_modules/oap-sdk/package.json'):
        if name not in files:
            raise ValueError('Built package is missing ' + name)
    # Same collision handling as the prebuilt packages: identities and icons only.
    files = installer.rename(files, original, app_id)
    target = installer.write_package(files, app_id, version, output)
    print("Built Korean Store package with the head unit's oap-sdk: " + str(target))
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--dir', required=True)
    parser.add_argument('--out', default=os.environ.get('MGU_OUT'))
    args = parser.parse_args()
    if not args.out:
        parser.error('MGU_OUT or --out is required')
    build(args.id, args.version, args.dir, args.out)


if __name__ == '__main__':
    main()

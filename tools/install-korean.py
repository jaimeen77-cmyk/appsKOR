#!/usr/bin/env python3
"""Assemble verified precompiled Korean files for MGU Store; no SDK or network."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
import uuid

ROOT = Path(__file__).resolve().parent.parent
ID = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
VERSION = re.compile(r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
LIMIT = 128 * 1024 * 1024


def inside(path):
    path = Path(path).resolve()
    if ROOT not in path.parents:
        raise ValueError('Path is outside the repository')
    return path


def read_layer(folder):
    folder = inside(folder)
    info = json.loads((folder / 'layer.json').read_text(encoding='utf-8'))
    if info.get('schema') != 1 or info.get('language') != 'ko':
        raise ValueError('Not a Korean compiled layer')
    parts = info.get('parts', [])
    if not parts or len(parts) > 128 or any(not re.match(r'^part-[0-9]{3}$', p) for p in parts) or len(set(parts)) != len(parts):
        raise ValueError('Invalid part list')
    data = b''.join((folder / p).read_bytes() for p in parts)
    if len(data) != info['size'] or hashlib.sha256(data).hexdigest() != info['sha256']:
        raise ValueError('Compiled layer checksum mismatch')
    # Read a bounded archive in memory; never extract package paths to disk.
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
        raw = compressed.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('Compiled layer exceeds the unpacked limit')
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        for member in archive:
            parts = PurePosixPath(member.name).parts
            if (not member.isfile() or not parts or parts[0] != 'package' or '..' in parts or
                    '\\' in member.name or 'node_modules' in parts or 'oap-sdk' in parts or
                    member.name in files or member.size > LIMIT):
                raise ValueError('Unsafe or duplicate compiled member: ' + member.name)
            files[member.name] = archive.extractfile(member).read()
    return info, files


def read_common(own):
    expected = own.get('common_sha256')
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('Invalid common layer identity')
    archived = ROOT / 'store/korean' / ('common-' + expected)
    common, files = read_layer(archived if archived.is_dir() else ROOT / 'store/korean/common')
    if common['sha256'] != expected:
        raise ValueError('Stale or mismatched common layer')
    return common, files


def assemble(app_id, version, directory, output):
    if not ID.fullmatch(app_id) or not VERSION.fullmatch(version):
        raise ValueError('Invalid app identity/version')
    directory = inside(ROOT / directory)
    listing = json.loads((directory / 'app.json').read_text(encoding='utf-8'))
    original = listing.get('sourceId')
    if not isinstance(original, str) or not ID.fullmatch(original) or listing['id'] != app_id or listing['version'] != version:
        raise ValueError('Store listing does not match requested package')
    own, delta = read_layer(ROOT / 'store/korean' / original)
    # Imported package cohorts can use different immutable runtimes. The full
    # digest selects the archived layer; the same checksum checks still apply.
    common, files = read_common(own)
    if own.get('id') != original or own.get('version') != version or own.get('common_sha256') != common['sha256']:
        raise ValueError('Stale or mismatched compiled package')
    if set(files).intersection(delta):
        raise ValueError('Compiled layers contain duplicate paths')
    files.update(delta)
    pkg = json.loads(files['package/package.json'].decode('utf-8'))
    locale = json.loads(files['package/javascript/kit/locale.json'].decode('utf-8'))
    if pkg['name'] != original or pkg['version'] != version or locale['language'] != 'ko':
        raise ValueError('Compiled identity/language mismatch')
    if 'package/javascript/app.js' not in files or 'package/javascript/kit/fonts/korean.json' not in files:
        raise ValueError('Compiled application or Hangul font is missing')
    # The Store can resolve an app-ID collision. Rewrite identities and icons,
    # preserving all application code, signal declarations and setting values.
    if app_id != original:
        replacements = {}
        for name, data in files.items():
            if name.endswith('/application.json'):
                for match in UUID.findall(data.decode('utf-8')):
                    replacements[match.lower()] = str(uuid.uuid5(uuid.NAMESPACE_URL, 'appsKOR:' + app_id + ':' + match.lower()))
        renamed = {}
        for name, data in files.items():
            if name.endswith(('.json', '.xml')) and (name.startswith('package/rhmiData') or name in {
                    'package/package.json', 'package/npm-shrinkwrap.json', 'package/manifest.json',
                    'package/permissions.json', 'package/config/base.json', 'package/javascript/kit/app-spec.json'}):
                def identity(value):
                    if isinstance(value, dict):
                        return {identity(k): identity(v) for k, v in value.items()}
                    if isinstance(value, list):
                        return [identity(v) for v in value]
                    if isinstance(value, str):
                        value = UUID.sub(lambda m: replacements.get(m.group(0).lower(), m.group(0)), value)
                        if value == original:
                            return app_id
                        if value.startswith(original + '_') and value.endswith('.png'):
                            return app_id + value[len(original):]
                        return value.replace('SID_' + original.upper() + '_', 'SID_' + app_id.upper() + '_')
                    return value
                text = data.decode('utf-8')
                if name.endswith('.json'):
                    data = (json.dumps(identity(json.loads(text)), ensure_ascii=False, indent=2) + '\n').encode('utf-8')
                else:
                    text = UUID.sub(lambda m: replacements.get(m.group(0).lower(), m.group(0)), text)
                    text = text.replace('SID_' + original.upper() + '_', 'SID_' + app_id.upper() + '_')
                    data = text.replace(original + '_icon.png', app_id + '_icon.png').encode('utf-8')
            basename = PurePosixPath(name).name
            if basename.startswith(original + '_') and basename.endswith('.png'):
                name = str(PurePosixPath(name).with_name(app_id + basename[len(original):]))
            if name in renamed:
                raise ValueError('Duplicate renamed package member')
            renamed[name] = data
        files = renamed
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Output folder must be empty')
    target = output / (app_id + '@' + version + '.tgz')
    with target.open('wb') as stream, gzip.GzipFile(filename='', fileobj=stream, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            for name in sorted(files):
                info = tarfile.TarInfo(name)
                info.size = len(files[name])
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(files[name]))
    print('Prepared Korean Store package: ' + str(target))
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
    assemble(args.id, args.version, args.dir, args.out)


if __name__ == '__main__':
    main()

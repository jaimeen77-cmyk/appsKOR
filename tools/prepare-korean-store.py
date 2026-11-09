#!/usr/bin/env python3
"""Publish Korean build stages as SDK-free, shared compiled Store layers."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parent.parent
CHUNK = 192 * 1024
DESCRIPTIONS = {
    'ambient_config': '앰비언트 조명 색상과 주행 모드별 색상 설정',
    'brake_test': '제동 구간의 시간과 거리 측정',
    'car_vitals': '엔진 회전수·출력·온도 등 실시간 차량 정보',
    'doom': '한국어 메뉴의 Doom · Freedoom Phase 1 데이터 포함',
    'draggy': '가속 구간 시간·거리와 주행 기록 측정',
    'dtc_scanner': '차량 고장 코드 조회와 진단 정보 확인',
    'dyno': '주행 데이터로 추정하는 출력·토크 그래프',
    'edrive': '전기 구동·고전압 배터리·차량 배터리 정보',
    'gforce': '가속·제동·코너링 G포스 표시',
    'live_adjustments': '지원 차량의 엔진·구동계·배기 관련 설정',
    'live_data': '차량 진단 신호와 실시간 데이터 표시',
    'redline': '회전수·기어·변속 알림과 HUD 표시',
    'service': '정비 항목·교환 시점·차량 서비스 정보',
    'warmup': '냉각수·오일 온도로 확인하는 엔진 예열 상태',
    'zf8hp': 'ZF 8HP 변속기 상태·온도·주행 정보',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inputs(app):
    # Untracked downloaded assets are represented by their checked asset specs.
    spec = json.loads((ROOT / 'apps' / app / 'app.json').read_text())
    downloaded = {a['file'] for a in spec.get('assets', [])}
    result = []
    folders = [ROOT / 'apps' / app, ROOT / 'kit/runtime', ROOT / 'kit/platform', ROOT / 'kit/localization']
    for folder in folders:
        for path in sorted(folder.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc' and not (path.parent == ROOT / 'apps' / app and path.name in downloaded):
                result.append((path.relative_to(ROOT).as_posix(), sha(path.read_bytes())))
    for name in ['build.py', 'localize.py', 'locale-revisions.json', 'pack_data.py']:
        p = ROOT / 'kit/tools' / name
        result.append((p.relative_to(ROOT).as_posix(), sha(p.read_bytes())))
    return sha(json.dumps(sorted(result), separators=(',', ':')).encode())


def layer(folder, files, **extra):
    data = io.BytesIO()
    with gzip.GzipFile(filename='', fileobj=data, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            for name, content in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size = len(content)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(content))
    payload = data.getvalue()
    folder.mkdir(parents=True, exist_ok=True)
    parts = []
    for index, offset in enumerate(range(0, len(payload), CHUNK)):
        name = 'part-' + str(index).zfill(3)
        (folder / name).write_bytes(payload[offset:offset + CHUNK])
        parts.append(name)
    for old in folder.glob('part-*'):
        if old.name not in parts:
            old.unlink()
    meta = dict(schema=1, language='ko', size=len(payload), sha256=sha(payload), parts=parts, **extra)
    (folder / 'layer.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n')
    return meta


def prepare(dist, source):
    # Validate every staged app before replacing any published layer.
    apps = {}
    for spec_path in sorted((ROOT / 'apps').glob('*/app.json')):
        app = spec_path.parent.name
        original = json.loads(spec_path.read_text())
        stage = dist / app / 'source'
        localized = json.loads((stage / 'javascript/kit/app-spec.json').read_text())
        locale = json.loads((stage / 'javascript/kit/locale.json').read_text())
        if locale['language'] != 'ko' or localized['version'] != original['version'] + '-ko.1':
            raise ValueError('Missing/stale Korean build: ' + app)
        files = {}
        for p in sorted(stage.rglob('*')):
            if not p.is_file() or 'node_modules' in p.relative_to(stage).parts:
                continue
            rel = p.relative_to(stage).as_posix()
            data = p.read_bytes()
            # Store's component parser requires x.y.z; label and resources stay
            # Korean. Only identity metadata versions lose the locale suffix.
            if p.suffix in ['.json', '.xml'] and (rel.startswith('rhmiData') or rel in ['package.json', 'npm-shrinkwrap.json', 'javascript/kit/app-spec.json']):
                data = data.decode('utf-8').replace(localized['version'], original['version']).encode('utf-8')
            files['package/' + rel] = data
        pkg = json.loads(files['package/package.json'])
        pkg.update(mguHmi=['ID7'], mguLocalOnly=True)
        files['package/package.json'] = (json.dumps(pkg, ensure_ascii=False, indent=2) + '\n').encode()
        if 'package/javascript/kit/fonts/korean.json' not in files or not any(n.endswith('/OFL-NotoSansKR.txt') for n in files):
            raise ValueError('Missing Hangul font/license: ' + app)
        apps[app] = dict(spec=original, localized=localized, files=files, source_hash=inputs(app))
    shared = dict(next(iter(apps.values()))['files'])
    for data in apps.values():
        shared = {n: b for n, b in shared.items() if data['files'].get(n) == b}
    common = layer(ROOT / 'store/korean/common', shared, source_commit=source)
    repo = json.loads((ROOT / 'mgu-repo.json').read_text())
    components = []
    for app, data in apps.items():
        spec = data['spec']
        own = {n: b for n, b in data['files'].items() if n not in shared}
        meta = layer(ROOT / 'store/korean' / app, own, id=app, version=spec['version'], compiled_version=data['localized']['version'], common_sha256=common['sha256'], source_commit=source, source_hash=data['source_hash'])
        listing = ROOT / 'store/apps' / app
        listing.mkdir(parents=True, exist_ok=True)
        manifest = dict(id=app, sourceId=app, version=spec['version'], title=data['localized']['title'] + ' (한국어)', description='한국어 고정 빌드 · ' + DESCRIPTIONS[app])
        (listing / 'app.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        shutil.copy2(ROOT / 'apps' / app / 'icon.png', listing / 'icon.png')
        components.append(dict(id=app, kind='app', path='store/apps/' + app, mguHmi=['ID7'], requires=dict({'mgu-deploy':'0.7.17'}, **repo.get('apps', {}).get('requires', {'idrive7-renderd':'2.1.7','mgu-inputgate':'1.0.0'})), build=dict(python='tools/install-korean.py', args=['--id','{id}','--version','{version}','--dir','{dir}'], network=False, shared=['tools/install-korean.py','store/korean/common','store/korean/' + app])))
        print(app + ': ' + str(meta['size']) + ' app bytes + shared Korean runtime; ' + data['localized']['version'])
    # Retain renderer/controller tools and their existing metadata unchanged.
    repo.pop('apps', None)
    repo['components'] = components
    (ROOT / 'mgu-repo.json').write_text(json.dumps(repo, ensure_ascii=False, indent=2) + '\n')
    print('Prepared %d Korean-only apps; common %d bytes.' % (len(apps), common['size']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    prepare(args.dist.resolve(), args.source_commit)

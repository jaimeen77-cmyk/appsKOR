#!/usr/bin/env python3
"""Localize the display text of IterioDev's prebuilt source packages."""
import argparse
import gzip
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'store/iteriodev-ko'
FONT = ROOT / 'kit/localization/fonts'
DESCRIPTIONS = {
    'cardash': '엔진, 연료, 변속기, DPF 데이터와 주행 기록을 확인합니다.',
    'draggy': '가속 기록과 출력 측정 결과를 확인합니다.',
    'dtcscan': '제어기 고장 코드와 체크 컨트롤 메시지를 확인합니다.',
    'edrive': '전기 주행 가능 거리, 배터리 상태와 충전 기록을 확인합니다.',
    'liveadjust': '지원 차량에서 엔진 맵, 배기 플랩 및 최대 냉각 설정을 조절합니다.',
    'overlays': '공조 바로가기, 시프트 라이트 및 M 모드 오버레이를 설정합니다.',
    'seats': '앞좌석 위치, 메모리 및 승하차 편의 설정을 조절합니다.',
    'service': '계기판의 정비 예정 항목을 확인합니다.',
    'tailscale': '헤드유닛의 Tailscale 연결 상태와 로그인 안내를 확인합니다.',
    'turnview': '전방 카메라 영상과 다음 회전 안내를 계기판에 표시합니다.',
    'oap-driverecorder-next': '차량 카메라 영상을 저장하고 정차 중에 재생하거나 USB로 복사합니다.',
}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Upstream text drawing changed: ' + old)
    return text.replace(old, new, 1)


def localize_renderer(files, prefix, words, font, license_text):
    def edit(name, edits):
        key = prefix + name
        text = files[key].decode('utf-8').replace('\r\n', '\n')
        for old, new in edits:
            text = replace(text, old, new)
        files[key] = text.encode('utf-8')

    files[prefix + 'kit/ko.js'] = (
        "'use strict';\n"
        "const catalog = require('./ko.json');\n"
        "const own = (text) => Object.prototype.hasOwnProperty.call(catalog, text);\n"
        "function translate(value) {\n"
        "    const text = String(value);\n"
        "    if (own(text)) return catalog[text];\n"
        "    if (text.indexOf('\\n') >= 0) return text.split('\\n').map(translate).join('\\n');\n"
        "    return text;\n"
        "}\n"
        "const family = (text, fallback) => /[\\uac00-\\ud7a3]/.test(text) ? 'korean' : fallback;\n"
        "module.exports = { translate, family };\n"
    ).encode('utf-8')
    files[prefix + 'kit/ko.json'] = json_bytes(words)
    files[prefix + 'kit/fonts/korean.json'] = font
    files[prefix + 'kit/fonts/OFL-NotoSansKR.txt'] = license_text
    require_fonts = "const fonts = require('./fonts');"
    require_ko = require_fonts + "\nconst ko = require('./ko');"
    edit('kit/record.js', [
        (require_fonts, require_ko),
        ("const family = opts.font || 'label';", "const s = ko.translate(str);\n        const family = ko.family(s, opts.font || 'label');"),
        ('const s = String(str), sc =', 'const sc ='),
        ("const f = fonts.get((opts && opts.font) || 'label', size * this.textScale);\n        const s = String(str);",
         "const s = ko.translate(str);\n        const f = fonts.get(ko.family(s, (opts && opts.font) || 'label'), size * this.textScale);"),
    ])
    edit('kit/canvas.js', [
        (require_fonts, require_ko),
        ("const f = fonts.get(opts.font || 'label', size);", "const s = ko.translate(str);\n        const f = fonts.get(ko.family(s, opts.font || 'label'), size);"),
        ('        const s = String(str);\n', ''),
        ("const f = fonts.get((opts && opts.font) || 'label', size);", "const s = ko.translate(str);\n        const f = fonts.get(ko.family(s, (opts && opts.font) || 'label'), size);"),
        ('fonts.measure(f, String(str))', 'fonts.measure(f, s)'),
        ('Math.max(0, String(str).length - 1)', 'Math.max(0, s.length - 1)'),
    ])
    edit('widgets.js', [
        ("'use strict';", "'use strict';\nconst { translate } = require('./kit/ko');"),
        ('    s = String(s);', '    s = translate(s);'),
        ("String(s || '').split(/\\s+/)", "translate(s || '').split(/\\s+/)"),
    ])


def read_package(path):
    files = {}
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive:
            name = member.name
            parts = PurePosixPath(name)
            if (not member.isfile() or parts.is_absolute() or '..' in parts.parts
                    or '\\' in name or name in files):
                raise ValueError('Unexpected archive entry ' + name)
            files[name] = archive.extractfile(member).read()
    return files


def write_package(path, files):
    with path.open('wb') as target:
        with gzip.GzipFile(filename='', fileobj=target, mode='wb', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as archive:
                for name, data in sorted(files.items()):
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o644
                    archive.addfile(info, io.BytesIO(data))
    if read_package(path) != files:
        raise ValueError('Package verification failed: ' + str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Checkout of iterio_fork')
    args = parser.parse_args()
    base = json.loads((ROOT / 'kit/runtime/locales/ko.json').read_text(encoding='utf-8'))
    words = {**{key.upper(): val for key, val in base.items()}, **base}
    words.update(dict(line.split('\t', 1) for line in (DATA / 'strings.tsv').read_text(encoding='utf-8').splitlines() if line))
    font = (FONT / 'korean.json').read_bytes()
    glyphs = json.loads(font)['sizes'][0]['glyphs']
    missing = sorted({ch for val in words.values() for ch in val if '가' <= ch <= '힣' and str(ord(ch)) not in glyphs})
    if missing:
        raise ValueError('Missing Korean glyphs: ' + ''.join(missing))
    font_license = (FONT / 'OFL-NotoSansKR.txt').read_bytes()
    repo_path = ROOT / 'mgu-repo.json'
    repo = json.loads(repo_path.read_text(encoding='utf-8'))
    existing = {c['id']: c for c in repo['components'] if not c['path'].startswith('store/iteriodev-ko/apps/')}
    iterio = []
    for short, description in DESCRIPTIONS.items():
        app_id = short if short.startswith('oap-') else 'iteriodev_' + short
        directory = args.source / 'apps' / app_id
        listing = json.loads((directory / 'app.json').read_text(encoding='utf-8'))
        if listing['id'] != app_id or app_id in existing:
            raise ValueError('Unexpected or conflicting app ID: ' + app_id)
        name = app_id + '@' + listing['version'] + '.tgz'
        files = read_package(directory / name)
        spec = json.loads(files['mgu-app.json'])
        assert spec['id'] == app_id and spec['version'] == listing['version']
        tree = spec['tree'] + '/'
        app_words = {key: val for key, val in words.items() if key.casefold() != listing['title'].casefold()}
        localize_renderer(files, tree + 'renderer/', app_words, font, font_license)
        for key in list(files):
            if not key.startswith(tree + 'rhmiData/') or not key.endswith('/en_GB.json'):
                continue
            strings = json.loads(files[key])
            if isinstance(strings, dict) and all(isinstance(v, str) for v in strings.values()):
                files[key.removesuffix('en_GB.json') + 'ko_KR.json'] = json_bytes({
                    k: app_words.get(v, v) for k, v in strings.items()
                })
        dest = DATA / 'apps' / app_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / 'app.json').write_bytes(json_bytes({
            **listing, 'description': '비공식 한국어 번역 · ' + description
        }))
        (dest / 'icon.png').write_bytes((directory / 'icon.png').read_bytes())
        write_package(dest / name, files)
        iterio.append({
            'id': app_id, 'kind': 'app', 'path': dest.relative_to(ROOT).as_posix(),
            'mguHmi': listing['mguHmi'], 'requires': listing.get('requires', {}),
            'uninstallable': True, 'build': {
                'node': 'store/iteriodev-ko/prebuilt.js',
                'output': '{dir}/{id}@{version}.tgz', 'network': False,
                'shared': ['store/iteriodev-ko/prebuilt.js'],
            },
        })
        print(app_id, listing['version'])
    (DATA / 'LICENSE.IterioDev.md').write_bytes((args.source / 'LICENSE.md').read_bytes())
    repo['components'] = [*existing.values(), *iterio]
    repo_path.write_bytes(json_bytes(repo))


if __name__ == '__main__':
    main()

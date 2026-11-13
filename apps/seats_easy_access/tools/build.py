#!/usr/bin/env python3
"""Build an SDK-free OAP package and a USB catalog. Python standard library only."""
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import sys
import tarfile
import uuid
import zipfile
import zlib

from rhmi_layout import build_ui, manifest_for, sid

ROOT = Path(__file__).resolve().parent.parent
ID = 'seats_easy_access'
VERSION = '0.3.2'
NS = uuid.UUID('367cc856-ae4d-4aef-b5a3-cd8b1997d25e')
LANGS = ['en_GB', 'en_US', 'ko_KR', 'de_DE']
ITEMS = [
    ['graphic', 'SEAT_GFX', 'seat-control.png'],
    ['text3', 'STATUS', 'Refresh the Comfort status first.'],
    ['twocol', 'SELECTED', 'Selected seat'],
    ['twocol', 'AUTO', 'Automatic Easy Access'],
    ['twocol', 'DRIVER', 'Driver seat'],
    ['twocol', 'PASSENGER', 'Passenger seat'],
    ['twocol', 'VEHICLE', 'Vehicle status'],
    ['button', 'REFRESH', 'Refresh status'],
    ['button', 'AUTO_TOGGLE', 'Turn automatic Easy Access on/off'],
    ['button', 'SLV_MINUS', '◀'], ['button', 'SLV_PLUS', '▶'],
    ['button', 'SHV_MINUS', '높이 ▼'], ['button', 'SHV_PLUS', '높이 ▲'],
    ['button', 'LNV_MINUS', '등받이 ◀'], ['button', 'LNV_PLUS', '등받이 ▶'],
    ['button', 'SNV_MINUS', '쿠션 ▼'], ['button', 'SNV_PLUS', '쿠션 ▲'],
    ['button', 'KHV_MINUS', '헤드레스트 ▼'], ['button', 'KHV_PLUS', '헤드레스트 ▲'],
    ['button', 'MEMORY_SAVE', '메모리 저장'],
    ['button', 'M1', 'M1'], ['button', 'M2', 'M2'], ['button', 'M3', 'M3'],
    ['button', 'EXIT_SAVE', '현재 위치를 하차 위치로 저장'],
    ['button', 'EXIT_MOVE', '하차 위치로 이동'],
    ['button', 'MAKE_ROOM', 'Make room · 조수석 공간 확보'],
    ['button', 'STOP', 'STOP seat movement'],
    ['text3', 'GUIDE', 'Park before saving or testing. Keep the seat path clear and the physical seat switch within reach.'],
]
KOREAN = {
    'TITLE': '시트', 'MAIN_TITLE': '시트',
    'STATUS': 'Comfort 상태를 먼저 확인하세요.',
    'SELECTED': '선택 시트', 'SELECT_DRIVER': '운전석', 'SELECT_PASSENGER': '조수석',
    'AUTO': '자동 Easy Access', 'DRIVER': '운전석', 'PASSENGER': '조수석', 'VEHICLE': '차량 상태',
    'REFRESH': '상태 새로 확인', 'AUTO_TOGGLE': '자동 Easy Access 켜기 / 끄기',
    'SLV_MINUS': '◀', 'SLV_PLUS': '▶', 'SHV_MINUS': '높이 ▼', 'SHV_PLUS': '높이 ▲',
    'LNV_MINUS': '등받이 ◀', 'LNV_PLUS': '등받이 ▶', 'SNV_MINUS': '쿠션 ▼', 'SNV_PLUS': '쿠션 ▲',
    'KHV_MINUS': '헤드레스트 ▼', 'KHV_PLUS': '헤드레스트 ▲',
    'MEMORY_SAVE': '메모리 저장', 'M1': 'M1', 'M2': 'M2', 'M3': 'M3',
    'EXIT_SAVE': '현재 위치를 하차 위치로 저장', 'EXIT_MOVE': '하차 위치로 이동',
    'STOP': '시트 이동 정지',
    'GUIDE': '저장과 시험은 정차 상태에서 하세요. 이동 경로를 비우고 순정 시트 스위치에 손이 닿게 하세요.',
}

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def uid(what):
    return str(uuid.uuid5(NS, ID + ':' + what))

def icon(path):
    w = h = 140
    pixels = [bytearray([16, 28, 48] * w) for _ in range(h)]
    def rect(x, y, width, height, color):
        for yy in range(y, y + height):
            for xx in range(x, x + width): pixels[yy][xx*3:xx*3+3] = bytes(color)
    rect(35, 25, 18, 62, (115, 195, 255))
    rect(45, 76, 54, 18, (115, 195, 255))
    rect(57, 98, 12, 15, (230, 240, 255))
    rect(30, 113, 73, 5, (230, 240, 255))
    def chunk(name, data):
        return struct.pack('!I', len(data)) + name + data + struct.pack('!I', zlib.crc32(name + data) & 0xffffffff)
    raw = b''.join(b'\x00' + bytes(row) for row in pixels)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', w, h, 8, 2, 0, 0, 0)) +
                     chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))

def archive(folder, output):
    with output.open('wb') as dest, gzip.GzipFile(fileobj=dest, mode='wb', mtime=0, filename='') as gz:
        with tarfile.open(fileobj=gz, mode='w') as tar:
            for file in sorted(folder.rglob('*')):
                if not file.is_file(): continue
                data = file.read_bytes()
                info = tarfile.TarInfo('package/' + file.relative_to(folder).as_posix())
                info.size = len(data); info.mode = 0o644; info.mtime = 0
                tar.addfile(info, io.BytesIO(data))

def main():
    dist = ROOT / 'dist'
    if dist.exists(): shutil.rmtree(dist)
    pkg = dist / 'staged'
    pkg.mkdir(parents=True)
    spec = {'id': ID, 'version': VERSION, 'title': 'Seats Easy Access', 'screens': [
        {'name': 'MAIN', 'kind': 'list', 'title': 'Seats Easy Access', 'items': ITEMS,
         'tabs': [['SELECT_DRIVER', '운전석'], ['SELECT_PASSENGER', '조수석']]}],
        'signals': {}}
    xml, ui, strings, _ = build_ui(spec)
    # Disabled in the installed resources as well as in the runtime policy.
    for container in ui['containers'].values():
        for component in container['components'].values():
            if component['name'] in ('AUTO_TOGGLE', 'SELECT_DRIVER', 'SELECT_PASSENGER',
                    'SLV_MINUS', 'SLV_PLUS', 'SHV_MINUS', 'SHV_PLUS', 'LNV_MINUS', 'LNV_PLUS',
                    'SNV_MINUS', 'SNV_PLUS', 'KHV_MINUS', 'KHV_PLUS', 'MEMORY_SAVE', 'M1', 'M2', 'M3',
                    'EXIT_SAVE', 'EXIT_MOVE', 'MAKE_ROOM'):
                component.setdefault('properties', {})['Enabled'] = {'value': 0, 'type': 'UInt'}
    pkg_json = {
        'name': ID, 'version': VERSION, 'description': 'Graphical seat controls, memories and Easy Access for iDrive 7',
        'main': 'javascript/app.js', 'license': 'MIT', 'author': 'Seats Easy Access contributors',
        'mguHmi': ['ID7'], 'engines': {'node': '>=8.7.0'},
        'oapAppSettings': {'maxDiskUsage': 2097152, 'cpuLimit': 15, 'memoryThresholdKB': 65536,
            'priority': 'PRIO_LOW', 'visibility': 'FOREGROUND', 'latencyClass': 'FOREGROUND',
            'loggingId': 'STST', 'userLoginRequired': False, 'backgroundPriority': 200, 'someipManifest': 'manifest.json'},
    }
    write_json(pkg / 'package.json', pkg_json)
    write_json(pkg / 'manifest.json', manifest_for(copy.deepcopy(spec)))
    write_json(pkg / 'npm-shrinkwrap.json', {'name': ID, 'version': VERSION, 'lockfileVersion': 1})
    write_json(pkg / 'config/base.json', {'rhmiLoadingEnabled': True, 'entryPointLoadingEnabled': True, 'settings': {ID: {}}})
    shutil.copytree(ROOT / 'src', pkg / 'javascript')
    shutil.copy(ROOT / 'vendor/permissions.json', pkg / 'permissions.json')
    shutil.copy(ROOT / 'LICENSE', pkg / 'LICENSE')
    shutil.copy(ROOT / 'NOTICE', pkg / 'NOTICE')
    shutil.copytree(ROOT / 'THIRD_PARTY_LICENSES', pkg / 'THIRD_PARTY_LICENSES')
    rhmi = pkg / 'rhmiData'
    write_json(rhmi / 'application.json', {'schemaVersion': '1.3.0', 'application': {
        'uuid': uid('app'), 'type': 'OnlineApp', 'name': ID, 'vendor': 'Seats Easy Access contributors',
        'version': VERSION, 'defaultLanguage': 'en_GB', 'stringBundleUuid': uid('strings'), 'resourceBundleUuid': uid('resources'),
        'entryPoints': [{'name': 'SEATS_EASY_ACCESS_ENTRY', 'uuid': uid('entry'), 'textId': sid(ID, 'TITLE'),
            'icon': ID + '_icon.png', 'insertionStateId': 20974, 'insertionFocusId': 2, 'insertionMode': 'INSERT_BELOW',
            'insertionOrder': 0, 'insertionPriority': 0, 'previewType': 'NONE', 'bookmarkable': True,
            'private': False, 'appearance': 'DEFAULT', 'isGroupHeader': False, 'insertionGroup': 0}],
        'uiDescriptions': [{'applicationFilePath': './uiDescriptions/ID7/application.xml',
            'uiDescriptionFilePath': './uiDescriptions/ID7/uiDescription.json', 'hmi': ['ID7']}],
        'variantGroups': [{'stringsPath': './variantGroups/Common/texts', 'resourcesPath': './variantGroups/Common/images',
            'hmi': ['ID7'], 'brands': ['BMW']}],
    }})
    write_json(rhmi / 'uiDescriptions/ID7/uiDescription.json', ui)
    (rhmi / 'uiDescriptions/ID7/application.xml').write_text(xml, encoding='utf-8')
    for lang in LANGS:
        translated = dict(strings)
        if lang == 'ko_KR': translated.update({sid(ID, key): value for key, value in KOREAN.items()})
        write_json(rhmi / ('variantGroups/Common/texts/' + lang + '.json'), translated)
    images = rhmi / 'variantGroups/Common/images'
    images.mkdir(parents=True); icon(images / (ID + '_icon.png'))
    shutil.copy(ROOT / 'assets/seat-control.png', images / 'seat-control.png')
    usb = dist / 'USB/mgu-repo/seats-easy-access'
    usb.mkdir(parents=True)
    package = usb / (ID + '@' + VERSION + '.tgz')
    archive(pkg, package)
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    write_json(usb / 'catalog.json', {'schema': 2, 'components': [{
        'id': ID, 'kind': 'app', 'version': VERSION, 'title': 'Seats Easy Access',
        'description': 'Save and control front-seat Easy Access positions.', 'mguHmi': ['ID7'],
        'uninstallable': True, 'requires': {'iteriodev-comfort': '0.5.1', 'mgu-deploy': '0.7.11'},
        'artifact': {'name': package.name, 'url': package.name, 'size': package.stat().st_size, 'sha256': digest},
    }]})
    shutil.copy(ROOT / 'README.ko.md', dist / 'USB/README.ko.md')
    (dist / 'USB/SHA256SUMS.txt').write_text(digest + '  mgu-repo/seats-easy-access/' + package.name + '\n')
    zip_path = dist / ('seats-easy-access-' + VERSION + '-usb.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for file in sorted((dist / 'USB').rglob('*')):
            if file.is_file(): z.write(file, file.relative_to(dist / 'USB'))
    print('Built ' + str(zip_path))
    print('Package SHA256 ' + digest)

if __name__ == '__main__': main()

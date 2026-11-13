"""Validate the delivered USB catalog, archive, native screen and command boundaries."""
import hashlib
import json
from pathlib import Path
import tarfile
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent
usb = root / 'dist/USB/mgu-repo/seats-easy-access'
catalog = json.loads((usb / 'catalog.json').read_text())
entry = catalog['components'][0]
package = usb / entry['artifact']['name']
assert entry['mguHmi'] == ['ID7']
assert entry['artifact']['size'] == package.stat().st_size
assert hashlib.sha256(package.read_bytes()).hexdigest() == entry['artifact']['sha256']
with tarfile.open(package) as archive:
    names = archive.getnames()
    assert all(n.startswith('package/') and '..' not in Path(n).parts for n in names)
    assert not any('/node_modules/' in n or n.endswith('hmictl') for n in names)
    def read(name): return archive.extractfile('package/' + name).read()
    pkg = json.loads(read('package.json'))
    assert pkg['name'] == entry['id'] and pkg['version'] == entry['version']
    assert pkg['mguHmi'] == ['ID7']
    assert 'package/' + pkg['main'] in names
    assert json.loads(read('config/base.json'))['rhmiLoadingEnabled'] is True
    ET.fromstring(read('rhmiData/uiDescriptions/ID7/application.xml'))
    ui = json.loads(read('rhmiData/uiDescriptions/ID7/uiDescription.json'))
    components = {c['name']: c for state in ui['containers'].values() for c in state['components'].values()}
    xml = ET.fromstring(read('rhmiData/uiDescriptions/ID7/application.xml'))
    bar = xml.find(".//layoutGroup[@name='Bar']")
    assert bar is not None and len(bar.findall('component')) == 2
    for name in ['SELECT_DRIVER', 'SELECT_PASSENGER']:
        assert components[name]['type'] == 'button'
    for name in ['AUTO_TOGGLE', 'SELECT_DRIVER', 'SELECT_PASSENGER', 'SLV_MINUS', 'SLV_PLUS',
                 'SHV_MINUS', 'SHV_PLUS', 'LNV_MINUS', 'LNV_PLUS', 'SNV_MINUS', 'SNV_PLUS',
                 'KHV_MINUS', 'KHV_PLUS', 'MEMORY_SAVE', 'M1', 'M2', 'M3', 'EXIT_SAVE', 'EXIT_MOVE', 'MAKE_ROOM']:
        assert components[name]['properties']['Enabled']['value'] == 0
    assert b'seat-control.png' in read('rhmiData/uiDescriptions/ID7/uiDescription.json')
    korean = json.loads(read('rhmiData/variantGroups/Common/texts/ko_KR.json'))
    assert '시트' in korean['SID_SEATS_EASY_ACCESS_TITLE']
    manifest = json.loads(read('manifest.json'))
    assert not any('Tasu' in iface for iface in manifest['proxies'])
    assert 'de.bmw.infotainment.vehicle.Vehicle2' not in manifest['proxies']
    assert 'de.bmw.infrastructure.VehicleInformation' not in manifest['proxies']
    assert b'iteriodev-comfort' in read('NOTICE')
print('PASS USB hash, OAP structure, RHMI XML/JSON, Korean resources, disabled movement controls and license notices')

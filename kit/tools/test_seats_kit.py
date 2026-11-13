"""Exercise make_kit end-to-end with an explicitly nonfunctional SDK fixture."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='seats-kit-test-') as temporary:
    root = Path(temporary)
    for name in ('kit', 'deploy'):
        shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT / 'apps/seats_easy_access', root / 'apps/seats_easy_access',
                    ignore=shutil.ignore_patterns('dist', '__pycache__'))
    sdk = root / 'oap-sdk'
    sdk.mkdir()
    (sdk / 'index.js').write_text("throw new Error('TEST FIXTURE: not a vehicle SDK');\n")
    (sdk / 'package.json').write_text('{"name":"oap-sdk","version":"0.0.0-test"}')
    result = subprocess.run([sys.executable, 'kit/tools/make_kit.py', 'seats_easy_access', '--language', 'ko', '--no-renderer'],
                            cwd=root, input='', text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    bundles = list((root / 'dist/mgu-custom-apps-ko/apps').glob('seats_easy_access@*.mgu'))
    assert len(bundles) == 1
    with tarfile.open(bundles[0]) as archive:
        names = archive.getnames()
        assert 'source/node_modules/oap-sdk/index.js' in names
        assert 'rhmiData/uiDescription/application.xml' in names
        assert 'oapgen/gen.js' in names
        meta = json.load(archive.extractfile('meta.json'))
        pkg = json.load(archive.extractfile('source/package.json'))
        assert meta['version'] == pkg['version'] and '-ko.' in meta['version']
    kit = root / 'dist/mgu-custom-apps-ko'
    for line in (kit / 'KIT_SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        assert hashlib.md5((kit / name).read_bytes()).hexdigest() == digest
    with tarfile.open(root / 'dist/mgu-custom-apps-ko.tar.gz') as archive:
        assert 'mgu-custom-apps/apps/' + bundles[0].name in archive.getnames()
    print('PASS make_kit: .mgu, version, resources, SDK inclusion, KIT_SUMS, full kit archive')
    print('SDK fixture only: no real vehicle runtime or installation was tested.')

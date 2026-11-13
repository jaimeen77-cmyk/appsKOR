"""Adapt the independent Seats package to the existing .mgu kit contract."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tarfile

from localize import package_version


def build_seats(root, language, preview_only=False):
    root = Path(root)
    if language != 'ko':
        raise SystemExit('Seats는 한국어판만 제공합니다. --language ko를 사용하세요.')
    sdk = root / 'oap-sdk'
    if not preview_only and not all((sdk / name).is_file() for name in ('index.js', 'package.json')):
        raise SystemExit('BMW oap-sdk is missing. Extract it from your own head unit, or use --preview-only.')
    folder = root / 'apps/seats_easy_access'
    tools = folder / 'tools'
    # The independent generator imports its own RHMI module, not the shared generator.
    sys.path.insert(0, str(tools))
    try:
        spec = importlib.util.spec_from_file_location('seats_package_build', tools / 'build.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        builder.main()
    finally:
        sys.path.pop(0)
    version = package_version(json.loads((folder / 'app.json').read_text(encoding='utf-8'))['version'], language)
    stage = root / 'dist/seats_easy_access'
    if stage.exists():
        shutil.rmtree(stage)
    source = stage / 'source'
    shutil.copytree(folder / 'dist/staged', source)
    for name in ('package.json', 'npm-shrinkwrap.json'):
        file = source / name
        data = json.loads(file.read_text(encoding='utf-8'))
        data['version'] = version
        file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    application = source / 'rhmiData/application.json'
    app = json.loads(application.read_text(encoding='utf-8'))
    app['application']['version'] = version
    app['application']['defaultLanguage'] = 'ko_KR'
    application.write_text(json.dumps(app, ensure_ascii=False), encoding='utf-8')
    rhmi = stage / 'rhmiData'
    (rhmi / 'uiDescription').mkdir(parents=True)
    shutil.copytree(source / 'rhmiData/uiDescriptions/ID7', rhmi / 'uiDescription', dirs_exist_ok=True)
    shutil.copytree(source / 'rhmiData/variantGroups/Common/texts', rhmi / 'strings')
    shutil.copytree(source / 'rhmiData/variantGroups/Common/images', rhmi / 'resources')
    app['application'].update({
        'entryPointsStringBundleUuid': app['application']['stringBundleUuid'],
        'entryPointsResourceBundleUuid': app['application']['resourceBundleUuid'],
        'externalDialogStringBundleUuid': app['application']['stringBundleUuid'],
    })
    (rhmi / 'application.json').write_text(json.dumps(app), encoding='utf-8')
    (stage / 'meta.json').write_text(json.dumps({'id': 'seats_easy_access', 'version': version,
        'title': '시트 Easy Access', 'native': [], 'kit': 1}), encoding='utf-8')
    shutil.copytree(root / 'kit/tools/oapgen', stage / 'oapgen')
    if preview_only:
        print('Seats preview staged:', stage)
        return
    shutil.copytree(sdk, source / 'node_modules/oap-sdk')
    for suffix, names in (('mgu', ['meta.json', 'source', 'rhmiData', 'oapgen']), ('tgz', ['source'])):
        output = root / 'dist' / ('seats_easy_access@' + version + '.' + suffix)
        with tarfile.open(output, 'w:gz') as archive:
            for name in names:
                archive.add(stage / name, arcname='package' if suffix == 'tgz' else name)
        print('Built:', output)

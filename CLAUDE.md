# appsKOR 작업 규칙

이 저장소는 `jaimeen77-cmyk/appsKOR_fork`(원본 `cauliflowermossgrape/idrive7-apps`의 포크)를 그대로 가져와
앱 15개(`apps/*`)를 한국어 Store 패키지(`store/apps/*`, `store/korean/*`)로 배포합니다.

## 버전과 iDrive 7 / iDrive 8 (mguHmi)

요청에 따로 적혀 있지 않아도 항상 원본 저장소의 설정을 그대로 따릅니다.

- 앱 버전은 `appsKOR_fork`의 `apps/<id>/app.json` `version`과 같아야 합니다. 이 저장소에서 따로 올리지 않습니다.
- `mguHmi`는 `appsKOR_fork`의 `apps/<id>/app.json` `mguHmi`를 따릅니다.
  값이 없으면 iDrive 7 전용(`["ID7"]`)이며 iDrive 8에 노출하지 않습니다.
- `mgu-repo.json`의 `mguHmi`만 손으로 고치지 않습니다. 설치 패키지 안의 `package.json`에도 같은 값이 들어가야
  iDrive 8에서 설치가 거부되지 않습니다(`... is for iDrive 7; this head unit is iDrive 8`).

## 원본 갱신 절차

1. `appsKOR_fork`의 `main`을 병합합니다. 원본 파일(`apps/`, `kit/` 등)은 고치지 않습니다.
   한국어 번역(`kit/runtime/locales/ko.tsv` → `python3 kit/tools/sync_locales.py ko`)과
   Store 빌드를 위한 `kit/tools/build.py`의 미리보기 단계 변경만 이 저장소의 것입니다.
2. `python3 kit/tools/build.py --preview-only --language ko <앱>`으로 15개 앱을 빌드합니다.
3. `python3 tools/prepare-korean-store.py --source-commit <appsKOR_fork 커밋>`:
   패키지와 목록의 버전·`mguHmi`를 원본 `app.json`에서 가져옵니다.
4. 검증: `python3 kit/tools/test_ko.py`, `python3 tools/test-korean-store.py --build`
   (목록·패키지·원본의 버전이나 `mguHmi`가 다르면 실패합니다).
5. `README.ko.md`, `README.md`의 버전 표와 `docs/APPS-MIGRATION.ko.md`를 갱신합니다.

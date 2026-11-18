# appsKOR 작업 규칙

## iDrive 7 / iDrive 8 (mguHmi)

요청에 따로 적혀 있지 않아도 항상 원본 저장소의 설정을 그대로 따릅니다.

- 한국어 앱 18개(`apps/*`, Store `store/apps/*`): `jaimeen77-cmyk/appsKOR_fork`의 `apps/<id>/app.json` `mguHmi`.
  값이 없으면 iDrive 7 전용(`["ID7"]`, 예: 클러스터 앱 3개)이며 iDrive 8에 노출하지 않습니다.
- IterioDev 한국어판(`store/iteriodev-ko/*`): `jaimeen77-cmyk/iterio_fork`의 `apps/<id>/app.json` `mguHmi`.
- `mgu-repo.json`의 `mguHmi`만 손으로 고치지 않습니다. 설치 패키지 안의 `package.json`에도 같은 값이 들어가야
  iDrive 8에서 설치가 거부되지 않습니다(`... is for iDrive 7; this head unit is iDrive 8`).

## 원본 갱신 절차

1. `appsKOR_fork`의 `main`을 병합합니다.
2. `python3 kit/tools/build.py --preview-only --language ko <앱>`으로 18개 앱을 빌드합니다.
3. `python3 tools/prepare-korean-store.py --source-commit <appsKOR_fork 커밋>`:
   패키지와 목록의 `mguHmi`를 원본 `app.json`에서 가져오고, IterioDev 목록은 유지합니다.
4. IterioDev 갱신은 `python3 tools/prepare-iteriodev-ko.py`(iterio_fork 체크아웃 사용)로 합니다.
5. 검증: `python3 kit/tools/test_ko.py`, `python3 tools/test-korean-store.py --build`
   (목록·패키지·원본의 `mguHmi`가 다르면 실패합니다).
6. 패키지 내용이 바뀌었는데 버전이 같은 앱은 버전을 올려 iDrive 7 설치본도 업데이트되게 합니다.
7. `README.ko.md`, `README.md`의 버전 표와 `docs/APPS-MIGRATION.ko.md`를 갱신합니다.

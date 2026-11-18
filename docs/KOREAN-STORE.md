# 한국어 MGU Store 배포

`mgu-repo.json`은 `store/apps/<id>/app.json`의 한국어 목록만 노출합니다. 원본 `apps/` 소스는 보존합니다. 기존 GPU 렌더러와 컨트롤러 도구 항목도 유지합니다.

Store는 원본 `appsKOR_fork`처럼 앱을 **차에서 빌드합니다**(`"sdk": "oap-sdk"`). `tools/build-korean.py`가 원본 `kit/tools/build.py`로 `apps/<sourceId>`를 한국어로 빌드합니다. 이때 그 차량의 `oap-sdk`가 `node_modules/oap-sdk`에 들어가고, SOME/IP manifest가 차량의 인터페이스 목록에 맞춰집니다. 패키지 버전(`x.y.z`)·`mguHmi`·한국어 설명은 `prepare-korean-store.py`의 `store_identity`가 정합니다.

공통 글꼴·런타임은 `store/korean/common`, 앱별 완성된 UI·코드·데이터는 `store/korean/<id>`에 나눠 보관합니다. 이 레이어는 설치에 쓰지 않고, 차량 빌드 결과를 확인하는 기준입니다(`tools/install-korean.py`로 SDK 없는 패키지를 조립해 비교).

앱 15개는 `appsKOR_fork`의 원본 그대로이며 버전도 같습니다. 소스 커밋은 [갱신 기록](APPS-MIGRATION.ko.md)을 확인하세요.

## 다시 생성

SDK 없이 `--preview-only`로 한국어 화면과 패키지 내용을 만듭니다. SDK 파일이나 SDK 포함 `dist/*.mgu`, `dist/*.tgz`는 공개하지 않습니다.

```sh
python kit/tools/test_ko.py
python kit/tools/build.py --preview-only --language ko
python tools/prepare-korean-store.py --dist dist --source-commit <빌드한_소스_커밋>
python tools/test-korean-store.py --build --car
```

공개 대상은 `mgu-repo.json`, `store/apps`, `store/korean`, 이 문서와 `tools/install-korean.py`, `tools/prepare-korean-store.py`, `tools/test-korean-store.py`입니다. SDK와 개인 차량 파일은 포함하지 않습니다. `.github/workflows/korean-localization.yml`에서도 패키지의 체크섬·원본 소스 일치 여부를 검사합니다. 원본 앱/번역/런타임을 갱신했다면 공개 레이어도 다시 생성해야 합니다.

스토어 버전과 완성된 패키지 버전은 동일한 `x.y.z`입니다. 한국어 컴파일 버전(`x.y.z-ko.1`)과 소스 입력 해시는 레이어 메타데이터로 기록합니다. Store의 충돌 ID 기능으로 별도 ID를 선택하면 패키지·RHMI·아이콘 식별자를 함께 변경하며 앱 신호와 설정 값은 유지합니다.

## 범위

`appsKOR_fork` 앱 15개의 메뉴·설정·한국어 런타임을 포함합니다. Doom에는 SHA-256으로 확인한 Freedoom 데이터를 포함하며 해당 앱의 원래 라이선스와 NOTICE도 함께 실립니다. 번역이 없는 차량 원문 데이터까지 자동 번역하는 기능은 아닙니다. 실제 차량 설치·출력 확인은 별도입니다.

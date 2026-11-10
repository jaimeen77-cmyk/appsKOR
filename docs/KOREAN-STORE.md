# 한국어 MGU Store 배포

`mgu-repo.json`은 `store/apps/<id>/app.json`의 한국어 목록만 노출합니다. 원본 `apps/` 소스는 보존합니다. 기존 GPU 렌더러와 컨트롤러 도구 항목도 유지합니다.

공통 글꼴·런타임은 `store/korean/common`, 앱별 완성된 UI·코드·데이터는 `store/korean/<id>`에 나눠 보관합니다. 각 레이어의 크기와 SHA-256을 설치 전에 검증합니다. `tools/install-korean.py`는 빌드된 파일을 묶는 역할만 하며 네트워크·차량 신호 접근·SDK 복사를 하지 않습니다. Store 설치 단계가 차량 SDK를 준비합니다.

## 다시 생성

본인 차량에서 추출한 SDK를 로컬 `oap-sdk/`에 준비한 다음 실행합니다. SDK 파일이나 SDK 포함 `dist/*.mgu`, `dist/*.tgz`는 공개하지 않습니다.

```sh
python kit/tools/test_ko.py
python kit/tools/build.py --language ko
python tools/prepare-korean-store.py --dist dist --source-commit <빌드한_소스_커밋>
python tools/test-korean-store.py --build
```

공개 대상은 `mgu-repo.json`, `store/apps`, `store/korean`, 이 문서와 `tools/install-korean.py`, `tools/prepare-korean-store.py`, `tools/test-korean-store.py`입니다. SDK와 개인 차량 파일은 포함하지 않습니다. `.github/workflows/korean-localization.yml`에서도 패키지의 체크섬·원본 소스 일치 여부를 검사합니다. 원본 앱/번역/런타임을 갱신했다면 공개 레이어도 다시 생성해야 합니다.

스토어 버전과 완성된 패키지 버전은 동일한 `x.y.z`입니다. 한국어 컴파일 버전(`x.y.z-ko.1`)과 소스 입력 해시는 레이어 메타데이터로 기록합니다. Store의 충돌 ID 기능으로 별도 ID를 선택하면 패키지·RHMI·아이콘 식별자를 함께 변경하며 앱 신호와 설정 값은 유지합니다.

## 범위

18개 앱의 메뉴·설정·한국어 런타임을 포함합니다. 일반 앱 15개는 `appsKOR_fork`, 클러스터 앱 3개는 `appscluster_fork`에서 통합했습니다. Doom에는 SHA-256으로 확인한 Freedoom 데이터를 포함하며 해당 앱의 원래 라이선스와 NOTICE도 함께 실립니다. 클러스터 앱의 계기판 글꼴은 차량 렌더러의 전송 한도를 지키기 위해 핵심 표기용 한글만 포함합니다. 번역이 없는 차량 원문 데이터까지 자동 번역하는 기능은 아닙니다. 실제 차량 설치·출력 확인은 별도입니다.

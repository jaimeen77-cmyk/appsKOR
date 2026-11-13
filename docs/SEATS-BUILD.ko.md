# Seats 키트 빌드

최신 저장소의 `apps/seats_easy_access`와 `kit/tools`를 사용하세요. 예전에 설치한 간이 dispatcher로 공용 build.py를 덮어쓴 경우 저장소의 원본 파일로 업데이트해야 합니다.

```powershell
python.exe .\kit\tools\make_kit.py seats_easy_access --language ko --no-renderer
```

`oap-sdk/index.js`와 `oap-sdk/package.json`이 필요합니다. SDK는 본인 차량에서 추출하며 배포하지 않습니다.

출력: `dist/mgu-custom-apps-ko.tar.gz`, `dist/mgu-custom-apps-ko/apps/seats_easy_access@0.3.2-ko.*.mgu`. Comfort는 별도로 설치해야 합니다.

패키지 빌드만 필요하면 `python kit/tools/build.py --language ko seats_easy_access`를 사용합니다. `.mgu`와 `.tgz`를 모두 생성합니다.

`python kit/tools/test_seats_kit.py`는 임시 폴더의 명시적인 테스트 SDK로 전체 키트 생성과 체크섬을 검사합니다. 실제 SDK의 실행이나 실차 설치 검사는 아닙니다. 테스트 SDK를 설치용으로 사용하지 마세요.

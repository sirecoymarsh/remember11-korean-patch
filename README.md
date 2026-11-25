# Remember11 한국어 패치 — Gestalt Edition

Remember11 PC판에 **Gestalt 1.3.0 추가 콘텐츠**와 한국어 번역을 통합한 비공식 패치입니다.

## 번역 원칙

- 본편 대사·선택지·화자명은 **일본어 PC 원문**을 기준으로 번역했습니다.
- TIPS와 연표는 **일본어 PSP 원문**을 기준으로 번역했습니다.
- 영어는 일본어 원문만으로 구조를 확인할 수 없는 Gestalt 기술 배열과 경계 확인에만 참고했습니다.
- 모든 의미 번역과 교정은 `Codex internal`이 직접 작성했으며 외부 번역 모델/API를 사용하지 않았습니다.

## 추가·변경 사항

원판(PC판 『Remember11 -the age of infinity-』) 대비 이 패치가 바꾸는 내용을 정리했습니다(기존 「적용 범위」 절을 이 절로 넓혔습니다). 괄호 안은 근거 파일이고, 확실하지 않은 항목은 「(추정)」으로 표시했습니다.

### 번역 범위

- **방식**: 원판의 영어 패치 슬롯(`R11-English.exe`, `FILE\*-en.afs`)을 한국어로 바꾼 별도 실행 파일 `R11-Korean-Gestalt.exe`를 만듭니다. 일본어 실행 파일과 일본어 슬롯은 그대로 둡니다 (`manifests/language_contract.json`).
- **본편 시나리오·선택지·화자명·백로그**: Gestalt 구조의 시나리오 문자열 34,910개 가운데 33,629개를 번역해 넣었습니다(일본어 PC판과 정확히 일치 33,070, 유사 일치 325, 수동 232+5). 제어 코드·문장부호뿐인 139개는 그대로 두었고, 미해결은 0입니다 (`manifests/release-validation.json` `scenario_map`).
- **선택지**: 336개. 색상 제어 문자를 넣지 않아 `%000F` 같은 코드가 화면에 보이지 않습니다.
- **TIPS**: PSP 일본어판 110항목·273페이지를 번역해 PC판 269페이지 자리에 맞춰 넣었습니다 (`source/gestalt/tips-ko.json`, `docs/FINAL-REPORT-KO.md`).
- **연표**: Gestalt 전용 연표 48페이지 (`source/gestalt/chronology-ko-pages.json`).
- **고정 UI·실행 파일 UI**: 고정 UI 문자열 2,651개 중 한국어 대상 1,039개, 실행 파일 안 문구 140개(참조 188곳: 메뉴 7개·대화상자 32개 포함. 예: 저장·불러오기·빠른 저장·빠른 불러오기·설정·TIPS·타이틀, 플레이 시간, 장면 달성률, 요일 표시, 「백 점프」) (`source/catalog/exe-ui-ko.json`, `release-validation.json` `executable_ui`).
- **이미지 UI**: 원문 글자를 지우고 원래 캔버스·비율·크기·위치에 맞춰 다시 만들었습니다(46자산·285블록, 박스 밖 변경 0). 대상은 설정·정보·앨범·음악·결과·타이틀 메뉴·텍스트·지도 설명·도움말 화면 부품과 배경(BG) 이미지 30개, 이벤트 이미지 1개입니다 (`source/ui-rendered/`, `docs/GESTALT-ANALYSIS-KO.md`).
- **Gestalt 1.3.0 추가 콘텐츠**: Gestalt Special Mode, 추가 배경 35개, 추가 BGM(`bgmpc-en.afs`, `bgmpc.afs`), 추가 영상(`movie\mved3.avi`)을 함께 넣었습니다. 추가 BGM·영상은 Gestalt 원본 파일을 그대로 복사합니다 (`source/adapter/build_gestalt_release.py`).
- **번역 원문**: 본편은 일본어 PC판(`FILE/mac.afs`), TIPS·연표·인물 정보는 일본어 PSP판. 영어는 Gestalt의 기술 배열·페이지 경계 확인과, 일본어판에도 영어로만 들어 있는 연출 문구·Gestalt 전용 영어 문구에만 썼습니다 (`language_contract.json`).
- **음성·영상 자막**: 음성은 원본 그대로입니다. 영상 자막 번역에 대한 기록은 없습니다 (추정: 해당 없음).

### 편의 기능

게임 안에 새 기능을 넣지는 않았습니다. 원판의 빠른 저장·빠른 불러오기·백 점프 같은 메뉴는 이름만 한국어로 바꿨습니다.

### 단축키·조작

원판과 같습니다.

### 화면·그래픽 개선

- **한글 글꼴**: 게임 글꼴 `FNT2626.FOP`의 쓰지 않는 칸과 안 쓰는 한자 칸에 한글 1,374자를 그려 넣었습니다(CP932 코드를 빌려 쓰는 방식). 가나·문장부호·영문·영어 슬롯용 떠다니는 글자 188자(0x8640~0x86FC)는 보호했습니다. 글꼴은 Noto Sans KR 굵기 500, 원본 34px 전각 칸·행간·배치에 맞췄습니다 (`language_contract.json`, `source/adapter/r11_font.py`).
- **글자 렌더링**: PC 원판처럼 밝은 글자 + 어두운 외곽선으로 그립니다.
- **실험용 도구(배포판 반영 여부 (추정))**: 대화창 배경 투명도를 높이는 `window_opacity.py`, 800×600에서 축소 표시를 미리 보정하는 `presharpen.py`, 굵기별 글꼴 바꿔 끼우기 파일을 만드는 `font_variants.py`가 있습니다. 출력 위치가 `runtime-test`라 v1.0.0 ZIP에는 들어가지 않은 것으로 보입니다.

### 버그 수정

- **한글이 검고 뭉쳐 보이던 문제**: 일반 대사마다 넣던 강제 검정색 코드 `%C000F` 때문에 엔진의 어두운 외곽선 위에 검은 글자가 겹쳐 획이 뭉쳤습니다. 이 코드를 없애고 원판 렌더링을 쓰게 했습니다 (`docs/FINAL-REPORT-KO.md`).
- **글리프 농도 반전·위치 문제**: 앞선 빌드는 한글 글자를 뒤집힌 농도표로 그려 옅은 획에 검은 테두리가 생겼고, 34px 칸이 아니라 48px 저장 칸 가운데에 놓였습니다. `refont.py`로 글자 그림만 다시 만들었습니다(번역·포인터는 그대로) (`source/adapter/refont.py`. v1.0.0에 반영됐는지는 (추정), 기본 굵기 500이 배포판과 같음).
- **선택지에 제어 문자가 그대로 보이던 문제**: 선택지 렌더러는 색상 명령을 글자로 찍기 때문에 선택지에는 색상 코드를 넣지 않습니다(336개 검증, 강제 검정 0).

### 설치·제거 방식

- **설치**: GitHub 릴리스 `v1.0.0`의 `Remember11-Korean-Gestalt.zip`(1,306,597,241바이트, SHA-256 `035f4901…`)을 받습니다. 원본 게임 폴더의 `R11-English.exe`, `FILE\*-en.afs`, `FILE\init.rp`, `FILE\movie`를 따로 백업한 뒤, ZIP 안 `Remember11-Korean-Gestalt` 폴더 내용을 게임 폴더에 복사하고 `R11-Korean-Gestalt.exe`를 실행합니다.
- **원본 확인**: 설치 도구가 원본 해시를 검사하지는 않습니다. 빌드할 때 쓴 원본·Gestalt 파일 해시는 `manifests/patch-manifest.json`에 기록돼 있습니다.
- **`init.rp`**: 원본 표를 그대로 두고 한국어 문자열을 뒤에 덧붙인 뒤, 검사한 포인터 317개(TIPS 269, 연표 48)만 새 문자열로 돌렸습니다(211,403 → 282,378바이트).
- **제거**: 백업한 파일을 되돌리고 `R11-Korean-Gestalt.exe`를 지웁니다.
- **필요 조건**: Remember11 PC판(영어 패치 슬롯이 있는 판). Gestalt 1.3.0 내용은 패치에 들어 있습니다. 특정 판매처(스팀 등) 판본 여부는 문서에 없습니다 (추정).

### 판(버전)별 변경 기록

| 판 | 날짜 | 변경 |
| --- | --- | --- |
| 내부 기본판·Gestalt판 | 2026-08-13 | 기본판(`Remember11-Korean.zip`)과 Gestalt판을 따로 만들어 실행 확인. Gestalt판은 128.5초 이상 응답, 오류 대화상자 0. 이 단계 글꼴은 굵기 600 (`docs/GESTALT-ANALYSIS-KO.md`). 기본판은 공개하지 않았습니다. |
| `v1.0.0` | 2026-08-24 | 첫 GitHub 배포판(Gestalt판만). 일본어 PC/PSP 원문 기준 번역, Gestalt 1.3.0 통합, 대사·선택지·TIPS·연표·메뉴·설정·이미지 UI 한국어화, 선택지 제어 문자 제거, 밝은 글자 + 어두운 외곽선, Noto Sans KR 500 (`54d3c1a`, `RELEASE_NOTES.md`). |

### 알려진 문제

- 실행 확인은 창 생성·응답 유지 수준(약 2분)이며 끝까지 플레이한 기록은 없습니다.
- 용어집 `source/glossary/glossary.json`은 초안 상태(항목 0개)입니다.
- 일반판(Gestalt 없는 판)은 공개되지 않았습니다.
- 두 문서의 숫자가 조금 다릅니다(실행 파일 UI 참조 155/188, 글꼴 굵기 600/500). 최종 수치는 `release-validation.json` 기준 188·500입니다.

## 다운로드 및 설치

1. GitHub의 [v1.0.0 릴리스](../../releases/tag/v1.0.0)에서 `Remember11-Korean-Gestalt.zip`을 받습니다.
2. 원본 게임 폴더의 `R11-English.exe`, `FILE\*-en.afs`, `FILE\init.rp`, `FILE\movie`를 별도 폴더에 백업합니다.
3. ZIP 내부 `Remember11-Korean-Gestalt` 폴더의 내용을 게임 폴더에 복사합니다.
4. `R11-Korean-Gestalt.exe`를 실행합니다.

일본어 실행 파일과 일본어 슬롯은 수정하지 않습니다. 복원할 때는 백업 파일을 되돌리고 `R11-Korean-Gestalt.exe`를 삭제합니다.

## 무결성

```text
SHA-256  035f490198e1203d44125a026ae8b52a7800699f6530d975967f92eeaa80468d
파일     Remember11-Korean-Gestalt.zip
크기     1,306,597,241 bytes
```

## 검증 요약

- 패키지 통합 검증: PASS
- 시나리오 문자열: 34,910
- 미해결 시나리오 매핑: 0
- 선택지 제어문자 제거 검증: 336개
- 강제 검정 선택지: 0개
- `init.rp` 포인터: 317개
- 한글 캐리어 글리프: 1,374개
- 실행 파일 UI 참조: 188개

자세한 내용은 [최종 보고서](docs/FINAL-REPORT-KO.md)와 [패치 매니페스트](manifests/patch-manifest.json)를 참조하십시오.

## 저장소 구성

- `source/adapter` — 아카이브·폰트·실행 파일·스크립트 빌드/검증 코드
- `source/translations` — 안정 ID 단위 한국어 번역 패킷
- `source/gestalt` — 통합 시나리오/TIPS/연표 번역 맵
- `source/ui-rendered` — 원문 제거 후 재제작한 UI 입력 자산
- `manifests` — 언어 계약, 출력 해시, 번역 provenance
- `release` — 릴리스 해시 파일(대용량 ZIP은 GitHub Release에만 첨부)

## 권리 고지

Remember11과 원본 게임 자산의 권리는 각 권리자에게 있습니다. 이 저장소는 비공식 한국어화 작업물이며 게임 원본을 대체하지 않습니다. 저장소의 게임 유래 데이터와 패치 산출물에 별도의 재라이선스를 부여하지 않습니다.

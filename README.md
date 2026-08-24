# Remember11 한국어 패치 — Gestalt Edition

Remember11 PC판에 **Gestalt 1.3.0 추가 콘텐츠**와 한국어 번역을 통합한 비공식 패치입니다.

## 번역 원칙

- 본편 대사·선택지·화자명은 **일본어 PC 원문**을 기준으로 번역했습니다.
- TIPS와 연표는 **일본어 PSP 원문**을 기준으로 번역했습니다.
- 영어는 일본어 원문만으로 구조를 확인할 수 없는 Gestalt 기술 배열과 경계 확인에만 참고했습니다.
- 모든 의미 번역과 교정은 `Codex internal`이 직접 작성했으며 외부 번역 모델/API를 사용하지 않았습니다.

## 적용 범위

- 본편 시나리오, 선택지, 화자명, 백로그
- TIPS 110개 및 연표 48페이지
- 메뉴, 설정, 저장/불러오기, 시스템 대화상자, 실행 파일 UI
- 원문 글자를 제거하고 원래 캔버스·비율·위치에 맞춰 다시 만든 이미지 UI
- Gestalt Special Mode와 추가 BG/BGM/동영상
- Noto Sans KR 500 한글 글꼴
- PC 원판과 같은 **밝은 글자 + 어두운 외곽선** 렌더링

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

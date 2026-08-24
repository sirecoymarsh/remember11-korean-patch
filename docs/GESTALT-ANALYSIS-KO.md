# Remember11 한국어판 — Gestalt Edition 최종 대조·통합 기록

## 최종 판정

Gestalt Edition 1.3.0은 분석 단계가 아니라 **별도 한국어 실행판으로 통합 완료**했다.

- 일반판: `release\Remember11-Korean.zip`
- 게슈탈트판: `release\Remember11-Korean-Gestalt.zip`
- 의미 기준: 본편은 일본어 PC 원문, 추가 TIPS·연표는 PSP 일본어 원문
- 영어 사용: 포인터 배열과 고정 페이지 경계처럼 일본어 PC판에 없는 기술 구조 확인에만 한정

## 통합 결과

| 영역 | 최종 결과 |
|---|---|
| 시나리오 | Gestalt 구조 34,910문자열 분석, 33,629개 번역 이식, 제어·문장부호 전용 139개 유지, 미해결 0 |
| 선택지 | 336개 검증, 색상 제어문자 노출 0, 선택지 검은색 강제 0 |
| TIPS | PSP 일본어판 110항목·273원문 페이지 번역; PC 기본판 265포인터, Gestalt 269포인터에 재배치 |
| 연표 | Gestalt 전용 48페이지 한국어화 |
| `init.rp` | 기본판 331포인터, Gestalt 383포인터를 append-only 방식으로 재구성·검증 |
| EXE UI | 155참조·139고유 대상·메뉴 7개·대화상자 32개 검증 |
| 이미지 UI | 46자산·285블록; 원문 글자 제거 후 원래 박스 안에서 재생성, 박스 밖 변경 0 |
| 폰트 | Noto Sans KR 34px/600, 기본판 1,373·Gestalt 1,374 한글 캐리어, 영어 플로팅 188자 보호 |
| 추가 미디어 | `bgmpc-en.afs`, `bgmpc.afs`, `movie\mved3.avi` 포함 |

## 배경/UI 충돌

Gestalt가 바꾸는 BG 35개와 한국어 UI가 바꾸는 BG 30개는 인덱스 중복이 0개다. Gestalt 배경을 기반으로 한국어 UI 엔트리를 항목 단위로 병합했으므로 양쪽 변경을 모두 보존했다.

## 포인터·제어 코드 처리

- 시나리오 풀은 EOF까지 확장 가능한 Gestalt 전용 재빌더로 재구성했다.
- 정렬된 16비트 포인터와 선택지 테이블을 함께 재배치했다.
- `init.rp`는 원본 테이블을 보존하고 한국어 문자열을 뒤에 추가한 뒤, 감사된 32비트 포인터만 새 문자열로 돌렸다.
- 선택지에는 `%000F`, `%FFFF` 같은 색상 제어문자를 넣지 않아 제어문자가 화면에 보이지 않는다.

## 실행 확인

2026-08-13에 P 드라이브의 전체 게임 테스트 복사본에서 최신 패키지를 각각 배치해 실행했다.

- 기본판: `Remember 11` Direct3D 창 생성, 응답 유지, 오류 대화상자 0
- Gestalt: `Remember11 - Gestalt Edition` Direct3D 창 생성, 128.5초 이상 응답 유지, 오류 대화상자 0
- 최근 R11 크래시 덤프 0

세부 근거는 `audit\final-runtime-report.json`, `build\final\release-validation.json`, `build\gestalt\release-validation.json`에 있다.

## 패키지 해시

- `Remember11-Korean.zip`: `f70d7fb5a54ddd6a7a7ba10801397a946d442efafb2c1d732f05a3bb98921765`
- `Remember11-Korean-Gestalt.zip`: `646f72499d3ce1cf6ee1c2be385f15a1874d0e6effb8072a3a6842e6dea22520`

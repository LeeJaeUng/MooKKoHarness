# MooKKoDev 하네스 설계 (Rust 판)

정한 날: 2026-10-29. 사용자 결정: 하네스를 MooKKoDev C# 복사판이 아니라 **Rust로 새로** 만든다("기술스택도 다 달라질꺼야"), 화면은 Vite + React + TypeScript + Tailwind CSS(정적 빌드를 Rust 서버가 서빙, 운영에 Node 없음), 이름에 Rust를 붙이지 않는다. 관리 대상은 제품 저장소 MooKKo(Rust 판). 저장소 경로는 설정 JSON에서 읽는다.

운영 교훈의 근거: `docs/reference/windows-runtime.md`(MooKKoDev C# 실행부가 10-19~10-27에 겪고 고친 것), `docs/reference/worker-isolation-plan.md`.

## 하는 일

1. 담당(역할)과 일감을 관리하고, 일감이 있을 때만 AI 워커를 띄운다.
2. AI 매니저에서 자리를 빌려 워커 한 턴을 돌리고, 끝나면 자리부터 반납한다.
3. 워커 커밋이 담당 경로(`docs/coordination/owners.json`) 안인지 확인한다.
4. 개발과 **다른 엔진**에 QA를 맡기고, 호스트가 CI(`tools/validate-rust.py` + 웹 관문 + Trivy·OSV-Scanner·Semgrep)를 돌려 관문 판정을 계산한다.
5. 모두 통과한 정확한 후보 커밋만 제품 `main`에 fast-forward로 반영하고 원격에 push한다(AI·워커는 push하지 않음).
6. 화면에서 일감·흐름·워커·전달 경로·점검·설정·업데이트·사용자 결정을 보여 준다.

## 구조

```
crates/
  dev-core      타입: 담당, 일감, 보고서, 영수증, 관문 판정 (화면용 TS 타입도 여기서 생성)
  dev-config    JSON 설정 읽기, 포트·주소 정하는 순서(실행 인자 → 허브 → 설정)
  dev-store     상태 저장: 덧붙이기만 하는 사건 기록 + 화면용 투영 (redb, 순수 Rust)
  dev-hub       허브 클라이언트: 포트 조회, 프로그램 토큰 등록, 작업 중 표시
  dev-ai        AI 매니저 클라이언트: 자리 빌리기·반납, 대기표, 엔진 전환
  dev-git       git 명령(tokio 프로세스): 담당별 작업 폴더·브랜치, 변경 경로, 경계 판정
  dev-worker    워커 실행: 격리 환경에서 codex/claude CLI 한 턴, 기한, 자식 프로세스 정리
  dev-qa        CI 실행과 관문 판정(gates.json), QA 영수증
  dev-merge     후보 커밋 확인 뒤 main fast-forward·push
  dev-server    axum: /api/v1 JSON, /api/v1/events(SSE), /health, 정적 화면(SPA) 서빙
apps/
  mookko-dev    실행 파일(조립)
web/            Vite + React + TypeScript + Tailwind (pnpm)
rules/          담당별 규칙(워커에게 넘김)
defaults/       담당 구성 초안(roles.json)
tools/          CI 도구(Python): validate-rust.py, export-policy.py, security_tools.py
```

- 모든 crate 루트 `#![forbid(unsafe_code)]`, unwrap·expect·panic 금지(시험만 허용), 요청 경로에서 동기 대기 금지. 제품과 같은 lint·검사(fmt·clippy -D warnings·test·deny·audit)를 쓴다.
- 제품 엔진 crate는 다른 저장소라 직접 가져다 쓰지 않는다(프로젝트끼리는 HTTP로만). 같은 스택(axum·tokio·serde·tracing)과 같은 규칙으로 따로 짠다. 공유가 필요해지면 비공개 레지스트리로 배포한 버전을 받는다.

## 설정·주소

- 실행 인자 `--config <경로>`(기본 `data/runtime/config.json`, git 제외). 모든 칸 필수, 모르는 칸 거부.
- 주소·포트는 코드에 두지 않는다. 자기 포트는 공통 규칙 순서대로: 실행 인자(허브가 켤 때 넘김) → 허브 `GET /v1/ports/rustdev` → 설정의 값. 허브 주소와 AI 매니저 주소도 설정 JSON에서 읽는다(AI 매니저 주소는 허브 조회 우선).
- 토큰(`data/runtime/ai-manager.json`, `data/runtime/hub.json`)은 git에 넣지 않는다.

## 화면 (`web/`)

- Vite + React + TypeScript(strict) + Tailwind CSS. 경로: React Router. 서버 데이터: TanStack Query. 그래프(흐름·전달 경로): React Flow. 의존성은 최소로, 새 패키지는 필요·대안·라이선스를 적는다.
- 빌드 결과(`web/dist`)를 `dev-server`가 서빙한다. 없는 경로는 `index.html`. 운영에 Node 없음. 빌드는 Linux(WSL `MooKKo-Linux`)에서 한다.
- API 타입은 Rust 타입에서 생성(ts-rs)해 `web/src/api/generated/`에 둔다. 손으로 쓴 요청 형식을 두지 않는다.
- 실시간 갱신은 SSE(`/api/v1/events`)로 받는다(주기 새로고침 대신).
- 다른 내부 도구와 같은 모양: 왼쪽 메뉴, MooKKo 로고, SUIT 글꼴. **허브 프로그램 선택 상자는 로고 바로 밑**에 둔다. 허브 주소를 화면 코드에 두지 않기 위해, 서버가 `GET /api/v1/ui-config`로 허브 주소를 넘기고 화면이 그 값으로 `switcher.js`를 `data-current="rustdev"`, `data-target`(로고 밑)과 함께 붙인다.
- 화면 목록(복사판 기준): 일감(목록·필터·검색·새 일감·내 확인 필요), 흐름, 워커, 전달 경로, 정기 점검, 설정(모델·관리), 업데이트, 사용자 결정 패널.
- Windows 알림을 쓰지 않는다. 알릴 내용은 화면의 기록·확인함에 남긴다.

## 운영 교훈 → 처음부터 넣을 요구 (`docs/reference/windows-runtime.md`)

- 일감이 있을 때만 워커를 띄우고, 담당 하나는 한 번에 일감 하나. 전역 동시 수는 남은 메모리를 보고 정한다(적응형 상한).
- 턴이 끝나면 자식까지 끝낸 뒤 **AI 자리를 먼저 반납**하고, 그다음 git 결과·보고서를 기록한다. 실제 종료가 불명확하면 완료로 위장하지 않는다.
- 워커의 명시적 보고서만 일감을 done/blocked/failed로 바꾼다. AI 턴 성공을 QA 통과나 반영으로 세지 않는다.
- 경계 판정은 그 턴이 만든 커밋만 본다(`after ^before ^origin/main`, 병합 커밋 규칙 포함).
- QA는 다른 엔진, 정확한 후보 커밋, 관문 전부 판정. QA fail은 끝난 QA로 기록하고 개발 담당에게 되돌린다.
- 멈춘 턴(호스트 재시작 등)은 일감을 pending으로 되돌린다. AI 매니저 끊김은 담당 실패로 세지 않는다. 사용량 한도·로그인 실패는 매니저에 알린다.
- 담당 간 파일 전달은 커밋 SHA와 저장소 안 경로로만.
- 업데이트·재시작 준비는 새 배정을 먼저 멈추고, 진행 중 턴·git 결과·자리 반납 확인까지 기다린다.

## 단계

| 단계 | 끝난 상태 |
|---|---|
| H1 뼈대 | 설정·포트 정하기, `/health`, 정적 화면 서빙, SSE, 화면 틀(메뉴·로고·허브 선택 상자). 허브 담당에게 실행 방식 전달, 켜기 확인 |
| H2 담당·일감 | 사건 기록 저장, 담당 구성(roles.json) 읽기, 일감 만들기·상태·필터, 화면 일감 판 |
| H3 워커 한 턴 | AI 매니저 자리 빌리기·반납, 격리 환경에서 워커 한 턴, 보고서 반영, 경계 판정 |
| H4 QA·CI·반영 | 다른 엔진 QA, CI(Rust·웹 관문·호스트 검사), 영수증, main fast-forward·push |
| H5 넓히기 | 모든 담당, 서비스 담당 등록, 적응형 동시 수, 정기 점검, 업데이트 |

## 정해야 할 것 (사용자)

1. 하네스 서버를 어디서 돌릴지: Windows(공통 규칙 "내부 도구는 Windows", Windows용 Rust 빌드 도구 필요) 또는 WSL Linux(제품과 같은 빌드 환경, 허브가 `wsl.exe`로 켬). 코드는 어느 쪽이든 같다.
2. 워커 격리 위치: WSL Linux 컨테이너(Podman, 권장) 또는 Windows AppContainer.
3. 화면 표시 이름: C# MooKKoDev("MooKKo 데브")와 함께 도는 동안 구분할 이름. 허브 앱 id는 지금 `rustdev`(허브 담당 소유).

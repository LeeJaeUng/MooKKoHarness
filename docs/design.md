# MooKKoDev 하네스 설계 (Rust 판)

정한 날: 2026-10-29. 사용자 결정: 하네스를 MooKKoDev C# 복사판이 아니라 **Rust로 새로** 만든다. 이름에 Rust를 붙이지 않는다. 관리 대상은 제품 저장소 MooKKo(Rust 판). 저장소 경로는 설정 JSON에서 읽는다.

## 하네스의 역할

**하네스는 개발될 서비스들을 강하게 잡는다.** 워커(AI)가 정해진 방식대로만 개발하도록 규칙을 주고, 어긋난 커밋은 CI·관문·경계 판정에서 막아 `main`에 들어가지 못하게 한다. 하네스 자신은 화면이 없다(API와 실시간 알림만).

일의 흐름: 담당·일감 배정 → AI 매니저 자리 빌림 → 워커 한 턴(규칙 주입) → 경계 판정 → 다른 엔진 QA → 호스트 CI·관문 판정 → 영수증 → 제품 `main` fast-forward·push. 하나라도 실패하면 영수증이 없고 반영되지 않는다.

## 강제하는 것

모든 항목은 두 곳에서 막는다. (1) 워커가 매 턴 받는 규칙(`rules/`), (2) 후보 커밋에서 하네스가 직접 돌리는 검사(워커가 로컬에서 돌리는 것과 같은 제품 `scripts/ci/` + 하네스 `tools/validate-rust.py`). 워커가 "통과했다"고 보고해도 하네스가 다시 돌린 결과만 믿는다.

| 결정 (사용자) | 강제 방법 | 검사 |
|---|---|---|
| 모든 앱은 공용 서버 엔진 하나를 씀 | 서비스 crate는 엔진 crate만 의존. HTTP 서버·DB 드라이버·gRPC·HTTP 클라이언트 crate(axum, hyper, sqlx, tokio-postgres, tonic, reqwest 등)를 직접 의존하면 실패. 어댑터·실행 파일 crate 의존도 실패 | 제품 `check-boundaries.py`, `check-stack.py` |
| 전부 모듈화(포트·어댑터) | 새 바깥 시스템은 엔진 포트 + 어댑터 crate + 적합성 시험으로만 | `check-boundaries.py`, QA 관문 |
| 포트·주소는 JSON 설정에서만 | IP·localhost·URL·`host:port`·주소 생성 코드가 Rust 소스에 있으면 실패(시험 포함, 시험은 fixtures JSON) | `check-no-hardcoded-endpoints.py` |
| 웹 화면은 React + TypeScript + Tailwind (`web/` pnpm) | `web/` 밖의 화면 코드, 다른 화면 프레임워크(Vue·Svelte·Angular·jQuery·Solid 등), 다른 CSS 프레임워크(Bootstrap 등), npm/yarn lock 파일이 있으면 실패. Next.js는 공개 SEO 화면 앱에서만 | `check-stack.py`, WEB-01 |
| 내부 화면은 Vite SPA, 운영에 Node 없음 | 내부 화면 앱에 SSR 서버 코드 금지, 정적 빌드를 엔진이 서빙 | `check-stack.py`, QA |
| API 클라이언트는 `.proto`에서 생성 | 화면에서 손으로 쓴 fetch 요청 형식 금지(생성 패키지만) | QA 관문 WEB-01 |
| 제품은 Linux에서 돎 | 빌드·시험·검사는 Linux에서. Windows 결과는 통과로 세지 않음 | 하네스 CI 실행 위치 |
| 이름에 Rust를 붙이지 않음 | crate·실행 파일·이미지·설정 id에 `rust` 금지 | `check-stack.py` |
| 언어별 코딩 규약(Rust·프론트엔드·SQL·Protobuf·도구) | 규약 정본 `docs/policy/conventions/`와 언어별 AI 스킬. 규칙마다 막는 수단을 적음. lint를 주석으로 끄는 것은 예외 등록부(만료일)에 없으면 실패 | clippy·eslint·tsc 설정, `check-lint-escapes.py`, QA CONV-01 |
| 메모리 안전·오류 처리 | `#![forbid(unsafe_code)]`, unwrap·expect·panic 금지, clippy -D warnings | `check-forbid-unsafe.py`, clippy |
| 의존성 | cargo-deny·cargo-audit, pnpm audit·라이선스·출처, lock 고정 | deny·audit, WEB-01 |
| 담당 경로 | 그 턴이 만든 커밋이 담당 `owns` 밖을 건드리면 실패 | 하네스 경계 판정(`owners.json`) |
| 다른 엔진 QA | 개발 엔진과 같은 엔진의 QA 보고는 무효, 관문 9+1개 전부 판정 | 하네스 영수증 |
| 돈은 마지막 | 돈 서비스 담당은 앞 단계 인수 시험이 C# 판에서 통과하기 전에 만들지 않음 | PM 규칙, 서비스 등록 |

규칙을 바꿀 때: 제품 `AGENTS.md`·`docs/policy/`·`scripts/ci/`를 고치고, 하네스 `rules/`에 같은 내용을 넣고, 하네스 정책을 다시 내보낸다.

## 구조

```
crates/
  dev-config    JSON 설정, 포트 정하는 순서(실행 인자 → 허브 → 설정)          [H1 있음]
  dev-hub       허브 클라이언트: 포트 조회, 프로그램 토큰, 작업 중 표시          [H1 포트 조회]
  dev-server    axum: /health, /api/v1/*, /api/v1/events(SSE). 화면 없음        [H1 있음]
  dev-core      타입: 담당, 일감, 보고서, 영수증, 관문 판정
  dev-store     상태 저장: 덧붙이기만 하는 사건 기록 + 투영(redb, 순수 Rust)
  dev-ai        AI 매니저: 자리 빌리기·반납, 대기표, 엔진 전환
  dev-git       담당별 작업 폴더·브랜치, 그 턴의 커밋, 경계 판정
  dev-worker    격리 환경에서 codex/claude 한 턴, 규칙 주입, 기한, 자식 프로세스 정리
  dev-qa        CI 실행(제품 scripts/ci + validate-rust.py + 웹 관문 + Trivy·OSV·Semgrep), 관문 판정, 영수증
  dev-merge     후보 커밋 확인 뒤 main fast-forward·push
apps/mookko-dev 실행 파일
rules/          워커에게 주는 담당 규칙   defaults/ 담당 구성 초안   tools/ CI 도구(Python)
```

모든 crate 루트 `#![forbid(unsafe_code)]`, 제품과 같은 lint·검사. 제품 엔진 crate는 다른 저장소라 가져다 쓰지 않는다(프로젝트끼리는 HTTP로만).

## 운영 교훈 → 처음부터 넣을 요구 (`docs/reference/windows-runtime.md`)

- 일감이 있을 때만 워커를 띄우고, 담당 하나는 한 번에 일감 하나. 전역 동시 수는 남은 메모리를 보고 정한다.
- 턴이 끝나면 자식까지 끝낸 뒤 **AI 자리를 먼저 반납**하고, 그다음 git 결과·보고서를 기록한다.
- 워커의 명시적 보고서만 일감을 done/blocked/failed로 바꾼다. AI 턴 성공을 QA 통과나 반영으로 세지 않는다.
- 경계 판정은 그 턴이 만든 커밋만 본다(`after ^before ^origin/main`, 병합 커밋 규칙 포함).
- QA fail은 끝난 QA로 기록하고 개발 담당에게 되돌린다. 멈춘 턴은 pending으로 되돌린다. AI 매니저 끊김은 담당 실패로 세지 않는다.
- 담당 간 파일 전달은 커밋 SHA와 저장소 안 경로로만. 업데이트 전에는 새 배정을 멈추고 진행 중 턴·자리 반납까지 기다린다.

## 단계

| 단계 | 끝난 상태 |
|---|---|
| H1 뼈대 | 설정·포트, `/health`, SSE. 허브 담당에게 실행 방식 전달, 켜기 확인 |
| H2 강제 검사 | 제품 `check-stack.py`(엔진 우회·화면 스택·이름) + 하네스 CI가 제품 검사 전부를 후보 커밋에서 돌려 판정 |
| H3 담당·일감 | 사건 기록 저장, 담당 구성, 일감 상태 API |
| H4 워커 한 턴 | AI 매니저 자리, 격리 실행, 규칙 주입, 보고서, 경계 판정 |
| H5 QA·반영 | 다른 엔진 QA, 관문 판정, 영수증, main 반영 |

## 정해야 할 것 (사용자)

1. 하네스 서버 실행 위치: Windows(허브와 바로 연결, Windows용 Rust 빌드 도구 필요) 또는 WSL Linux(제품과 같은 빌드 환경, 허브에 닿게 WSL 네트워크 설정 필요).
2. 워커 격리 위치: WSL Linux 컨테이너(Podman, 권장) 또는 Windows AppContainer.

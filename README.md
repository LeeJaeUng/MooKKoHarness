# MooKKoHarness

공통 안내: MooKKo 폴더의 `CLAUDE.md`(이 저장소의 상위 폴더). AI 매니저와 허브는 쓰지 않습니다(사용자 2026-11-03, 개발은 Claude 앱 세션).

MooKKo 제품의 개발 하네스입니다. **개발될 서비스들이 정해진 방식대로만 개발되도록 강하게 잡는 것**이 역할입니다(`docs/design.md` › 강제하는 것). 정해진 방식은 공용 엔진, 모듈화, 설정 목록, React·TS·Tailwind 화면, Linux 빌드, Kubernetes 라이브입니다.

검사·관문·규약·AI 스킬의 정본이 여기 있습니다. 제품은 `harness.lock`에 이 저장소의 커밋을 고정하고, 얇은 진입점(`scripts/ci/check-all.sh`)으로 그 판을 돌립니다.

전에는 이름이 MooKKoRustDev였습니다. 2026-11-03 사용자 결정으로 바꾸고 제품의 검사를 여기로 모았습니다. 그 전 C# 하네스 MooKKoDev는 2026-10-30에 철거했습니다.

| 항목 | 값 |
|---|---|
| 허브 | 등록하지 않음(사용자 2026-11-03, 옛 id `rustdev`·포트 5292는 쓰지 않음) |
| 개발·워커 | Claude 앱 세션(PM → 하네스 담당 → 하위 세션). AI 매니저 안 씀 |
| 서버 | Rust(axum, tokio), H1 뼈대에서 멈춤(`docs/design.md` › 단계). 띄우지 않음 |
| 원격 | `LeeJaeUng/MooKKoHarness`(비공개, 만들면 PM이 처음 push) |
| 실행 데이터 | `data/` (git 제외) |

## 폴더

| 폴더 | 무엇 |
|---|---|
| `docs/` | 설계(`design.md`), 옛 판 기록(`reference/`) |
| `policy/` | 관문(`gates.md`·`gates.json`), 언어별 규약(`conventions/`) |
| `rules/` · `skills/` | 워커에게 주는 담당 규칙, 언어별 AI 스킬 |
| `ci/` | `check-all.sh`와 검사 본체, 검사 표본 |
| `dev/` | 개발 도구: 빌드 자리, 메모리·디스크 관문, 시험 DB, WSL 실행 |
| `config/` | 하네스 서버 설정 예, 개발 도구 설정(`dev/`), 담당 구성(`roles.json`: 세션·모델·owns, 읽는 프로그램 없음) |
| `apps/` · `crates/` | 하네스 서버(Rust, 멈춤) |

## 검사를 바꾸려면

1. 여기서 고치고 커밋합니다. 검사마다 잡아야 할 표본과 통과시켜야 할 표본이 `ci/fixtures/`에 있어야 합니다.
2. 제품 `harness.lock`을 그 커밋으로 올리고, 제품 사본(`docs/policy/gates.*`·`docs/policy/conventions/`·`.claude/skills/`)을 맞춥니다.
3. 제품 check-all을 통과시킵니다.

판을 올리는 것은 제품 통합 담당만 합니다. 판을 내리거나 검사를 약하게 바꾸는 것은 사용자 결정 없이는 실패입니다.

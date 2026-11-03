# 언어별 코딩 규약

MooKKo는 언어마다 규약을 따로 둡니다(사용자 결정 2026-10-29). 목표는 넷이고, 부딪히면 이 순서로 판단합니다.

1. **안정성** — 패닉·무한 대기·무제한 자원이 없고, 실패해도 무너지지 않는다.
2. **속도** — 멀티스레드를 최대로 쓰고, 막는 작업·잠금·복사·왕복을 줄인다. 잰 숫자로 판단한다.
3. **모듈화** — 포트·어댑터, 작은 단위 하나에 한 가지 일, 경계는 검사로 막는다.
4. **재사용** — 반복되는 패턴은 엔진·공용 패키지에 한 번만 만든다.

| 언어 | 규약 | AI 스킬 | 어디에 |
|---|---|---|---|
| Rust | [rust.md](rust.md) | `.claude/skills/mookko-rust/` | `crates/` |
| TypeScript·React·Tailwind (프론트엔드) | [frontend.md](frontend.md) | `.claude/skills/mookko-frontend/` | `web/` |
| SQL (PostgreSQL, ClickHouse — 로그·추적·지표) | [sql.md](sql.md) | `.claude/skills/mookko-sql/` | 각 crate `migrations/`(ClickHouse는 경로에 `clickhouse`가 든 `migrations/`) |
| 보안 (플랫폼·운영: 노드 풀·샌드박스·감지·대응·취약점) | [security.md](security.md) | `.claude/skills/mookko-security/` | `deploy/`, Kubernetes 매니페스트, IaC, 감지 규칙, `docs/policy/vuln-register.json`·`privileged-allowlist.json` |
| Protobuf | [proto.md](proto.md) | `.claude/skills/mookko-proto/` | `proto/` |
| Python·Bash (CI·시험 도구) | [tools.md](tools.md) | `.claude/skills/mookko-tools/` | `scripts/`, `acceptance/` 도구 |

## 강제 표시

규칙마다 무엇이 막는지 적습니다. 막는 수단이 있는 규칙은 어기면 커밋이 하네스 CI에서 실패해 `main`에 들어가지 못합니다.

| 표시 | 뜻 |
|---|---|
| **[lint]** | 컴파일러·clippy·eslint·tsc 규칙(`Cargo.toml` `[workspace.lints]`, `clippy.toml`, eslint 설정) |
| **[deny]** | 의존성 검사(`deny.toml`, `pnpm audit`, 라이선스) |
| **[검사]** | `ci/` 스크립트(이름을 함께 적음) |
| **[벤치]** | 벤치마크·부하 시험 기준(나빠지면 실패) |
| **[QA]** | 분야별 QA 세션 점검표(기계로 잡기 어려운 것) |

## 예외

규칙을 끄는 주석(Rust `#[allow]`·`#[expect]`, TS `eslint-disable`, `@ts-ignore`)은 시험 코드의 정해진 것 말고는 금지합니다. 꼭 필요하면 [`../lint-exceptions.json`](../lint-exceptions.json)에 파일·규칙·이유·만료일을 올리고 통합 담당 승인을 받습니다. 등록되지 않은 끄기는 `ci/check-lint-escapes.py`가 실패시킵니다.

참고한 공개 자료(내용을 옮기지 않고 우리 목표에 맞게 골라 다시 씀): Rust API Guidelines, leonardomso/rust-skills(MIT), apollographql/skills rust-best-practices(MIT), vercel-labs/agent-skills react-best-practices, C# 판 `docs/quality/code-quality-security-checklist.md`.

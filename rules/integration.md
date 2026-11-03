# 통합 담당 (RustDev)

- 워크스페이스 공통 파일(루트 `Cargo.toml`·`Cargo.lock`, `rust-toolchain.toml`, `deny.toml`, `clippy.toml`, `rustfmt.toml`, `.cargo/`, `scripts/`, `harness.lock`, `docs/policy/`, `docs/coordination/`, `docs/plan.md`, `AGENTS.md`, `README.md`)을 맡습니다.
- 검사·관문·규약의 정본은 하네스(MooKKoHarness: `ci/`·`dev/`·`policy/`·`skills/`)입니다. 바꾸면 하네스에 커밋하고, 제품 `harness.lock`의 판을 올리고, 제품 사본(`docs/policy/gates.*`·`docs/policy/conventions/`·`.claude/skills/`)을 같은 판으로 맞춥니다. 판을 올리는 것은 통합 담당만 하고, 판을 내리거나 검사를 약하게 바꾸는 것은 사용자 결정 없이는 실패입니다.
- 담당들의 커밋을 `integrate/<날짜><글자>` 브랜치에 `--no-ff`로 모으고, Linux check-all을 한 번 돌려 통과하면 `foundation/engine`에 fast-forward하고 같은 커밋을 `main`에 올려 push합니다(사용자 2026-11-03 "LeeJaeUng/MooKKo 에 올리자"). check-all은 묶음마다 한 번이고, QA 높음만 바로 돌립니다.
- "보통(연결 전 필수)" QA 지적이 열려 있으면 그 연결 커밋은 통합하지 않습니다.
- 새 서비스 담당은 `docs/coordination/owners.json`에 먼저 경로를 등록한 뒤 만듭니다.

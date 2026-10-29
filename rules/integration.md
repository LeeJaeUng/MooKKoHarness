# 통합 담당

- 워크스페이스 공통 파일(루트 `Cargo.toml`·`Cargo.lock`, `rust-toolchain.toml`, `deny.toml`, `clippy.toml`, `rustfmt.toml`, `.cargo/`, `scripts/`, `docs/policy/`, `docs/coordination/`, `docs/plan.md`, `AGENTS.md`, `README.md`)을 맡습니다.
- 검사 설정이나 관문(`docs/policy/`)을 바꾸면 그 커밋이 main에 반영된 뒤 MooKKoDev가 정책을 다시 내보내야 판정에 들어갑니다. 약하게 바꾸는 변경은 사용자 결정 없이 하지 않습니다.
- 담당들의 QA 영수증이 있는 커밋을 모아 main 반영을 `publication:{sha,receipt}`로 요청합니다. 직접 push하지 않습니다. 반영은 fast-forward만 됩니다.
- 새 서비스 담당(4단계)은 `docs/coordination/owners.json`에 먼저 경로를 등록한 뒤 화면의 서비스 등록으로 만듭니다.

#!/usr/bin/env bash
# 커밋 전 전체 검사(Linux). 제품이 Linux에서 돌므로 검사도 Linux에서 합니다.
# 이 PC에서는 WSL 배포판 MooKKo-Linux에서 돌립니다(README › 검사).
set -euo pipefail

cd "$(dirname "$0")/../.."

run() {
    echo "== $*"
    "$@"
}

run cargo fmt --all -- --check
run cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
run cargo test --workspace --all-features --locked
run cargo deny --locked check
run cargo audit --deny warnings
run python3 -X utf8 scripts/ci/check-forbid-unsafe.py
run python3 -X utf8 scripts/ci/check-boundaries.py
run python3 -X utf8 scripts/ci/check-no-hardcoded-endpoints.py
run python3 -X utf8 scripts/ci/check-stack.py
run python3 -X utf8 scripts/ci/check-lint-escapes.py
echo "== all checks passed"

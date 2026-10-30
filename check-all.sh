#!/usr/bin/env bash
# 커밋 전 전체 검사(Linux). 제품이 Linux에서 돌므로 검사도 Linux에서 합니다.
# 이 PC에서는 WSL 배포판 MooKKo-Linux에서 돌립니다(README › 검사).
set -euo pipefail

cd "$(dirname "$0")/../.."

# 로그인 셸이 아니면 rustup이 PATH에 cargo를 넣지 않습니다(WSL에서 bash -c로 부를 때).
if ! command -v cargo >/dev/null 2>&1 && [ -f "$HOME/.cargo/env" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.cargo/env"
fi

# 남은 공간이 기준 아래거나 빌드 캐시가 상한을 넘으면 빌드를 시작하지 않습니다(2026-10-30 C 드라이브 0 사고 뒤).
if [ -z "${MOOKKO_DISK_GUARD_DONE:-}" ]; then
    python3 -X utf8 scripts/dev/disk-guard.py
    export MOOKKO_DISK_GUARD_DONE=1
fi

# 저장소 어댑터 시험은 실제 PostgreSQL에 붙습니다. 접속 설정(MOOKKO_TEST_POSTGRES)이 없으면
# Podman으로 시험용 PostgreSQL을 잠깐 띄우고 그 안에서 이 검사를 다시 실행합니다(끝나면 지움).
if [ -z "${MOOKKO_TEST_POSTGRES:-}" ]; then
    exec scripts/dev/with-test-postgres.sh scripts/ci/check-all.sh "$@"
fi
export MOOKKO_REQUIRE_TEST_POSTGRES=1

run() {
    echo "== $*"
    "$@"
}

run cargo fmt --all -- --check
run cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
run cargo test --workspace --all-features --locked
run cargo deny --locked check
run cargo audit --deny warnings
run scripts/ci/check-public-api.sh
run python3 -X utf8 scripts/ci/check-forbid-unsafe.py
run python3 -X utf8 scripts/ci/check-boundaries.py
run python3 -X utf8 scripts/ci/check-no-hardcoded-endpoints.py
run python3 -X utf8 scripts/ci/check-stack.py
run python3 -X utf8 scripts/ci/check-lint-escapes.py
echo "== all checks passed"

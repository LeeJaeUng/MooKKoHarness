#!/usr/bin/env bash
# 커밋 전 전체 검사(Linux). 제품이 Linux에서 돌므로 검사도 Linux에서 합니다.
# 이 PC에서는 WSL 배포판 MooKKo-Linux에서 돌립니다(README › 검사).
set -euo pipefail
# git 기록·기준 판을 읽지 못하면 "건너뜀"이 아니라 실패(migration_lock 잠금 기록, vuln-register 기준 판 대조 ⑤). 보안 담당·QAManager
# 요청 2026-11-04. 표본 시험은 검사 폴더가 git 최상위가 아니라 대조 자체를 하지 않으므로 영향 없음.
export MOOKKO_REQUIRE_GIT_HISTORY="${MOOKKO_REQUIRE_GIT_HISTORY:-1}"

H="$(cd "$(dirname "$0")/.." && pwd)"  # 하네스 저장소 최상위
if [ -z "${MOOKKO_PRODUCT_ROOT:-}" ]; then
    echo "MOOKKO_PRODUCT_ROOT(검사할 제품 저장소)가 없습니다. 제품의 scripts/ci/check-all.sh(harness.lock 판)로 부르세요" >&2
    exit 2
fi
cd "$MOOKKO_PRODUCT_ROOT"

# 로그인 셸이 아니면 rustup이 PATH에 cargo를 넣지 않습니다(WSL에서 bash -c로 부를 때).
if ! command -v cargo >/dev/null 2>&1 && [ -f "$HOME/.cargo/env" ]; then
    . "$HOME/.cargo/env"
fi

# Windows에서 만든 worktree는 .git 파일이 C:/… 경로를 가리켜 WSL의 git이 읽지 못합니다(2026-11-03 links: 보안 관문
# git ls-files가 exit 128). 그 경로를 /mnt/<드라이브>/… 로 바꿔 GIT_DIR·GIT_WORK_TREE로 넘깁니다. 저장소 파일은 고치지 않습니다.
if [ -f .git ] && ! git rev-parse --git-dir >/dev/null 2>&1; then
    gitdir="$(sed -n 's/^gitdir: //p' .git | tr -d '\r')"
    case "$gitdir" in
        [A-Za-z]:/*)
            drive="$(printf '%s' "${gitdir%%:*}" | tr '[:upper:]' '[:lower:]')"
            export GIT_DIR="/mnt/$drive/${gitdir#?:/}"
            export GIT_WORK_TREE="$PWD"
            git rev-parse --git-dir >/dev/null
            echo "== Windows worktree: GIT_DIR=$GIT_DIR"
            ;;
    esac
fi

# 빌드 자리(대기표·메모리 관문·자리 캐시 규칙)는 dev/build-slot-acquire.sh 하나에 둡니다(dev/with-build-slot.sh와 함께 씀).
MOOKKO_SLOT_RUNNER="ci/check-all.sh"
source "$H/dev/build-slot-acquire.sh"

# 자기 캐시가 폴더 한도를 넘으면 자기 것만 지우고 새로 빌드하고, 여유가 모자라면 24시간 넘은 남의 캐시부터 지우고, 그래도 모자라면 빌드를 시작하지 않습니다
# (2026-10-30 C 드라이브 0 사고 뒤, dev/disk-guard.py).
if [ -z "${MOOKKO_DISK_GUARD_DONE:-}" ]; then
    python3 -X utf8 "$H/dev/disk-guard.py"
    export MOOKKO_DISK_GUARD_DONE=1
fi

# 저장소 어댑터 시험은 실제 PostgreSQL에 붙습니다. 접속 설정(MOOKKO_TEST_POSTGRES)이 없으면
# Podman으로 시험용 PostgreSQL을 잠깐 띄우고 그 안에서 이 검사를 다시 실행합니다(끝나면 지움).
if [ -z "${MOOKKO_TEST_POSTGRES:-}" ]; then
    exec "$H/dev/with-test-postgres.sh" "$H/ci/check-all.sh" "$@"
fi
export MOOKKO_REQUIRE_TEST_POSTGRES=1

# 빌드 중에는 메모리 사용률을 30초마다 기록하고 soft 이상이면 WSL page cache를 비웁니다. 끝날 때 최고값을 남깁니다.
python3 -X utf8 "$H/dev/memory-guard.py" watch &
MEMORY_WATCH=$!
trap 'kill "$MEMORY_WATCH" 2>/dev/null || true; wait "$MEMORY_WATCH" 2>/dev/null || true' EXIT

# 단계마다 시작 전에 메모리를 봅니다: hard 이상이면 내려갈 때까지 기다리고, soft 이상이면 cargo 작업 수를 줄입니다.
run() {
    CARGO_BUILD_JOBS="$(python3 -X utf8 "$H/dev/memory-guard.py" step "$1" "${MOOKKO_BASE_JOBS:-$CARGO_BUILD_JOBS}")"
    export CARGO_BUILD_JOBS
    echo "== $* (jobs $CARGO_BUILD_JOBS)"
    "$@"
}

run cargo fmt --all -- --check
run cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
run cargo test --workspace --all-features --locked
run cargo deny --locked check
run cargo audit --deny warnings
run "$H/ci/check-security-tools.sh"
run "$H/ci/check-public-api.sh"
run python3 -X utf8 "$H/ci/check-forbid-unsafe.py" "$PWD"
run python3 -X utf8 "$H/ci/check-boundaries.py" "$PWD"
run python3 -X utf8 "$H/ci/check-no-hardcoded-endpoints.py" "$PWD"
run python3 -X utf8 "$H/ci/check-stack.py" "$PWD"
run python3 -X utf8 "$H/ci/check-lint-escapes.py" "$PWD"
run python3 -X utf8 "$H/ci/check-test-tempdirs.py" "$PWD"
run python3 -X utf8 "$H/ci/check-dev-exposure.py" "$PWD"
run python3 -X utf8 "$H/ci/check-containers.py" "$PWD"
run python3 -X utf8 "$H/ci/check-file-size.py" "$PWD"
run python3 -X utf8 "$H/ci/check-engine-reuse.py" "$PWD"
# 하네스 정본과 제품 사본(관문·규약·스킬)이 같은지, 하네스 폴더 자리(둘 다 처음에는 경고, PM 2026-11-03).
run python3 -X utf8 "$H/ci/check-harness-copies.py" --warn "$PWD" "$H"
run python3 -X utf8 "$H/ci/check-folder-layout.py" --warn "$H"
run python3 -X utf8 "$H/ci/test_ci_checks.py"
run python3 -X utf8 "$H/ci/check-acceptance.py" "$PWD"
run python3 -X utf8 "$H/ci/check-design-sources.py" "$PWD"
run python3 -X utf8 "$H/ci/check-hardcoded-values.py" "$PWD"
run python3 -X utf8 "$H/ci/check-test-time.py" "$PWD"
run python3 -X utf8 "$H/ci/check-prr.py" "$PWD"
run python3 -X utf8 "$H/ci/check-production-config.py" "$PWD"
run python3 -X utf8 "$H/ci/check-waivers.py" "$PWD"
run python3 -X utf8 "$H/ci/check-vuln-register.py" "$PWD"
run python3 -X utf8 "$H/ci/check-security-reviews.py" "$PWD"
run python3 -X utf8 "$H/ci/check-systemd-units.py" "$PWD"
run "$H/ci/db/check-db.sh"
echo "== all checks passed"

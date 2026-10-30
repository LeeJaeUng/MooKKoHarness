#!/usr/bin/env bash
# 커밋 전 전체 검사(Linux). 제품이 Linux에서 돌므로 검사도 Linux에서 합니다.
# 이 PC에서는 WSL 배포판 MooKKo-Linux에서 돌립니다(README › 검사).
set -euo pipefail

cd "$(dirname "$0")/../.."

# 로그인 셸이 아니면 rustup이 PATH에 cargo를 넣지 않습니다(WSL에서 bash -c로 부를 때).
if ! command -v cargo >/dev/null 2>&1 && [ -f "$HOME/.cargo/env" ]; then
    . "$HOME/.cargo/env"
fi

# 빌드 자리: 여러 세션이 동시에 돌리면 WSL 메모리가 모자라 연결이 끊깁니다(2026-10-30). scripts/dev/build-slots.json의
# 자리 수만큼만 동시에 돌고 나머지는 기다립니다. 잠금은 이 프로세스와 자식(시험용 DB 감싸기 포함)이 끝나면 풀립니다.
if [ -z "${MOOKKO_BUILD_SLOT:-}" ]; then
    slot_setting() {
        python3 -I -c 'import json,os,sys; v=json.load(open(sys.argv[1],encoding="utf-8"))[sys.argv[2]]; print(os.path.expanduser(v) if isinstance(v,str) else v)' scripts/dev/build-slots.json "$1"
    }
    SLOT_DIR="$(slot_setting dir)"
    SLOT_COUNT="$(slot_setting count)"
    SLOT_POLL="$(slot_setting pollSeconds)"
    export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-$(slot_setting jobs)}"
    mkdir -p "$SLOT_DIR"
    announced=""
    while [ -z "${MOOKKO_BUILD_SLOT:-}" ]; do
        for i in $(seq 1 "$SLOT_COUNT"); do
            exec {slot_fd}>"$SLOT_DIR/slot-$i"
            if flock -n "$slot_fd"; then
                export MOOKKO_BUILD_SLOT="$i"
                break
            fi
            exec {slot_fd}>&-
        done
        if [ -z "${MOOKKO_BUILD_SLOT:-}" ]; then
            [ -z "$announced" ] && echo "== 빌드 자리 기다림(동시 ${SLOT_COUNT}개)"
            announced=1
            sleep "$SLOT_POLL"
        fi
    done
    echo "== 빌드 자리 $MOOKKO_BUILD_SLOT/$SLOT_COUNT, CARGO_BUILD_JOBS=$CARGO_BUILD_JOBS"
fi

# 빌드 캐시가 한도를 넘거나 공간이 모자라면 24시간 넘게 안 쓴 캐시부터 지우고, 그래도 모자라면 빌드를 시작하지 않습니다
# (2026-10-30 C 드라이브 0 사고 뒤, scripts/dev/disk-guard.py).
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
run scripts/ci/db/check-db.sh
echo "== all checks passed"

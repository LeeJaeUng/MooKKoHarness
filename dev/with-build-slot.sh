#!/usr/bin/env bash
# 빌드 자리를 잡고 그 안에서 명령 하나를 돌립니다(links·로그 요청 2026-11-04: 인수 시험 실행 기록, 시험 ClickHouse 실측).
# check-all과 같은 자리·대기표·메모리 관문(dev/build-slot-acquire.sh)과 디스크 관문을 거칩니다. 빌드 자리 밖 cargo는 금지이므로
# (PM 2026-11-02) check-all이 아닌 cargo·시험 컨테이너 실행은 이 입구로만 합니다.
#   scripts/dev/with-build-slot.sh [--postgres] [--clickhouse] -- <명령...>
#   --postgres    dev/with-test-postgres.sh 안에서 돌림(MOOKKO_TEST_POSTGRES)
#   --clickhouse  dev/with-test-clickhouse.sh 안에서 돌림(MOOKKO_TEST_CLICKHOUSE)
# 명령에는 CARGO_TARGET_DIR(자리 캐시)이 넘어갑니다. 예: `cargo build -p mookko-links && python3 acceptance/links/run-local.py
# --bin-dir "$CARGO_TARGET_DIR/debug" …`는 `bash -c '…'`로 넘깁니다.
set -euo pipefail

H="$(cd "$(dirname "$0")/.." && pwd)"
if [ -z "${MOOKKO_PRODUCT_ROOT:-}" ]; then
    echo "MOOKKO_PRODUCT_ROOT(제품 저장소)가 없습니다. 제품의 scripts/dev/with-build-slot.sh(harness.lock 판)로 부르세요" >&2
    exit 2
fi
cd "$MOOKKO_PRODUCT_ROOT"

postgres=""
clickhouse=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --postgres) postgres=1; shift ;;
        --clickhouse) clickhouse=1; shift ;;
        --) shift; break ;;
        *) break ;;
    esac
done
if [ "$#" -eq 0 ]; then
    echo "usage: $0 [--postgres] [--clickhouse] -- <명령...>" >&2
    exit 2
fi

MOOKKO_SLOT_RUNNER="dev/with-build-slot.sh"
source "$H/dev/build-slot-acquire.sh"

if [ -z "${MOOKKO_DISK_GUARD_DONE:-}" ]; then
    python3 -X utf8 "$H/dev/disk-guard.py"
    export MOOKKO_DISK_GUARD_DONE=1
fi

# 도는 동안 메모리 사용률을 기록하고 soft 이상이면 WSL page cache를 비웁니다(check-all과 같음).
python3 -X utf8 "$H/dev/memory-guard.py" watch &
MEMORY_WATCH=$!
trap 'kill "$MEMORY_WATCH" 2>/dev/null || true; wait "$MEMORY_WATCH" 2>/dev/null || true' EXIT

command=("$@")
if [ -n "$clickhouse" ]; then
    command=(bash "$H/dev/with-test-clickhouse.sh" "${command[@]}")
fi
if [ -n "$postgres" ]; then
    command=(bash "$H/dev/with-test-postgres.sh" "${command[@]}")
fi
echo "== 빌드 자리 $MOOKKO_BUILD_SLOT 안에서 실행: $*"
"${command[@]}"

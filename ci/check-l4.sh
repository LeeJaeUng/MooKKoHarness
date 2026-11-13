#!/usr/bin/env bash
# L4(출시 관문) 검사 입구(rust-qa 11-14 낮음 1): 평소 check-all에서 경고로 두는 것 가운데 출시 관문에서 실패로 올리는 검사들을 한 번에
# `--l4`로 돌린다. 지금 L4 모드가 있는 검사: check-security-reviews(만료·기록 없음), check-fuzz-targets(코드 없는 대상),
# check-acceptance(enforce 서비스의 기록 신선도), check-proto-compat(기준 판 대비 깨지는 proto 변경). check-all을 대신하지 않는다 — check-all을 통과한 판에 더 돌린다.
#   ci/check-l4.sh [제품 루트]       (MOOKKO_PRODUCT_ROOT가 있으면 그것)
# 하나라도 실패하면 1. 검사마다 결과 줄을 그대로 낸다.
set -euo pipefail

H="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="${1:-${MOOKKO_PRODUCT_ROOT:-$PWD}}"
ROOT="$(cd "$ROOT" && pwd)"
export MOOKKO_L4=1
export MOOKKO_REQUIRE_GIT_HISTORY=1

status=0
run() {
    echo "== L4: $*"
    "$@" || status=1
}
run python3 -X utf8 "$H/ci/check-security-reviews.py" --l4 "$ROOT"
run python3 -X utf8 "$H/ci/check-fuzz-targets.py" "$ROOT" --l4
run python3 -X utf8 "$H/ci/check-acceptance.py" "$ROOT" --l4
run python3 -X utf8 "$H/ci/check-proto-compat.py" "$ROOT" --l4
if [ "$status" -ne 0 ]; then
    echo "L4 checks failed"
    exit 1
fi
echo "== L4 checks passed"

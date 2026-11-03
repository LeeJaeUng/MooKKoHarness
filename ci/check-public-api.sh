#!/usr/bin/env bash
# 엔진 공개 API 고정(7단계): crates/engine/* 마다 공개 API를 crates/engine/<crate>/public-api.txt와 비교합니다.
# 서비스가 기대는 엔진 API가 모르게 바뀌지 않게 합니다. API를 일부러 바꿨으면
#   MOOKKO_BLESS_PUBLIC_API=1 scripts/ci/check-public-api.sh
# 로 스냅숏을 고쳐 같은 커밋에 올립니다(바뀐 줄이 리뷰에 보임).
# rustdoc JSON은 nightly에서만 나오므로 nightly 툴체인(rustup toolchain install nightly --profile minimal)과
# cargo-public-api(cargo install --locked cargo-public-api)가 필요합니다.
set -euo pipefail

cd "$(dirname "$0")/../.."

crates=$(python3 -I -c '
import json, subprocess, sys
meta = json.loads(subprocess.run(["cargo", "metadata", "--format-version", "1", "--no-deps", "--locked"],
                                 check=True, capture_output=True, text=True).stdout)
for p in meta["packages"]:
    if "/crates/engine/" in p["manifest_path"].replace("\\", "/") and any("lib" in t["kind"] for t in p["targets"]):
        print(p["name"])
')

if [ -z "$crates" ]; then
    echo "public API check failed: 엔진 crate를 하나도 찾지 못했습니다(cargo metadata 확인)"
    exit 1
fi

# cargo public-api 오류를 버리지 않고 받아 두었다가 실패하면 끝 몇 줄을 냅니다(mookko-rust-qa 11-03: 출력 없이 끝남).
mkdir -p "${TMPDIR:-/tmp}/mookko-test"
err="$(mktemp "${TMPDIR:-/tmp}/mookko-test/public-api.XXXXXX")"
trap 'rm -f "$err"' EXIT
status=0
for crate in $crates; do
    dir="crates/engine/$crate"
    snapshot="$dir/public-api.txt"
    # nightly rustdoc 산출물은 자리 캐시 안의 따로 된 폴더에 둡니다(check-all이 worktree가 바뀌면 통째로 버림).
    if ! current=$(CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-target}/public-api" cargo public-api -p "$crate" -ss --all-features 2>"$err"); then
        echo "public API check failed: cargo public-api -p $crate 이 실패했습니다:"
        tail -n 20 "$err"
        exit 1
    fi
    if [ "${MOOKKO_BLESS_PUBLIC_API:-}" = "1" ]; then
        printf '%s\n' "$current" > "$snapshot"
        echo "blessed $snapshot"
    elif [ ! -f "$snapshot" ]; then
        echo "missing $snapshot (run with MOOKKO_BLESS_PUBLIC_API=1)"
        status=1
    elif ! diff -u "$snapshot" <(printf '%s\n' "$current") > /dev/null; then
        echo "public API of $crate changed:"
        diff -u "$snapshot" <(printf '%s\n' "$current") || true
        status=1
    fi
done
if [ "$status" -eq 0 ]; then
    echo "public API check passed ($(echo "$crates" | wc -w) crates)"
fi
exit "$status"

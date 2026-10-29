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

status=0
for crate in $crates; do
    dir="crates/engine/$crate"
    snapshot="$dir/public-api.txt"
    current=$(cargo public-api -p "$crate" -ss --all-features 2>/dev/null)
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

#!/usr/bin/env bash
# 하네스 카나리(Linux, MooKKo-Linux 안에서). PM 지시 2026-11-04(사용자 "그렇게해") ①: 하네스를 바꾸면 공용 제품 체크아웃이 아니라
# 따로 둔 사본에서 먼저 check-all을 한 번 돌린다. 통과한 판만 통합 담당이 harness.lock으로 공용에 올린다.
# 그날 새 표본 시험이 check-all의 GIT_DIR을 물려받아 공용 .git/config를 망친 일(13:27)과 멈춘 실행이 자리를 쥔 일(13:33~16:45)을
# 공용 체크아웃에 닿기 전에 잡으려는 것이다.
#
#   dev/harness-canary.sh <제품 본 체크아웃> <하네스 본 저장소> <후보 하네스 커밋> [기준 브랜치, 기본 foundation/engine] [--prepare-only]
#
# - GIT_*·MOOKKO_* 환경을 모두 끊고 시작한다(우선순위만 CANARY_SLOT_PRIORITY, 기본 2).
# - 사본: /tmp/mookko-test/harness-canary/<시각>-<pid>/product 에 `git clone --shared --branch <기준>`(Linux 경로라 GIT_DIR 우회 없음).
#   사본의 harness.lock을 후보 커밋으로, 하네스 사본 자리(gates·conventions·skills)를 후보 판으로 맞춰 커밋한 뒤
#   scripts/ci/check-all.sh(빌드 자리를 거침)를 돌린다. 꺼낸 하네스 캐시도 사본 안 data/harness/에 둔다.
# - 공용 제품 .git/config의 sha256을 앞뒤로 견줘 바뀌었으면 실패.
# - 끝나면: 통과면 이 실행이 만든 사본 폴더를 바로 지운다(WSL /tmp 자기 실행분 예외, CLAUDE.md), 실패면 원인 확인용으로 남긴다.
# - --prepare-only: 사본을 만들고 맞추기까지만 하고 check-all은 돌리지 않는다(도구 자체 시험용, 끝나면 사본을 지움).
set -euo pipefail

for v in $(compgen -e); do
    case "$v" in GIT_*|MOOKKO_*) unset "$v" ;; esac
done

if [ "$#" -lt 3 ]; then
    sed -n '7,7p' "$0" >&2
    exit 2
fi
PRODUCT="$(cd "$1" && pwd)"
HREPO="$(cd "$2" && pwd)"
CAND="$(git -C "$HREPO" rev-parse --verify "$3^{commit}")"
BASE="foundation/engine"
PREPARE=""
for arg in "${@:4}"; do
    case "$arg" in
        --prepare-only) PREPARE=1 ;;
        *) BASE="$arg" ;;
    esac
done
[ -d "$PRODUCT/.git" ] || { echo "제품 본 체크아웃(.git 폴더가 있는 곳)이어야 합니다: $PRODUCT" >&2; exit 2; }

RUN="${TMPDIR:-/tmp}/mookko-test/harness-canary/$(date +%Y%m%d%H%M%S)-$$"
mkdir -p "$RUN"
config_hash() { sha256sum "$PRODUCT/.git/config" | cut -d' ' -f1; }
before="$(config_hash)"
echo "== 하네스 카나리: 후보 ${CAND:0:7}, 기준 $BASE, 사본 $RUN/product"

git clone -q --shared --branch "$BASE" "$PRODUCT" "$RUN/product"
cd "$RUN/product"
git config user.name "harness-canary"
git config user.email "canary@localhost"
# 기준 판 대조(owner-paths·vuln-register 등)가 foundation/engine을 읽으므로 사본에도 같은 이름으로 둔다.
[ "$BASE" = "foundation/engine" ] || git branch -q foundation/engine origin/foundation/engine
sed -i "s/^commit = .*/commit = $CAND/" harness.lock
# 하네스 사본 자리(ci/check-harness-copies.py PAIRS와 같음)를 후보 판으로 맞춘다.
EXTRACT="$RUN/harness"
mkdir -p "$EXTRACT"
git -C "$HREPO" archive "$CAND" policy/gates.md policy/gates.json policy/conventions skills | tar -x -C "$EXTRACT"
cp "$EXTRACT/policy/gates.md" "$EXTRACT/policy/gates.json" docs/policy/
rm -rf docs/policy/conventions .claude/skills
cp -r "$EXTRACT/policy/conventions" docs/policy/conventions
mkdir -p .claude
cp -r "$EXTRACT/skills" .claude/skills
rm -f .claude/skills/README.md
git add -A harness.lock docs/policy .claude/skills
git commit -q -m "canary: 하네스 ${CAND:0:7}" || true

rc=0
if [ -z "$PREPARE" ]; then
    MOOKKO_HARNESS_REPO="$HREPO" MOOKKO_SLOT_PRIORITY="${CANARY_SLOT_PRIORITY:-2}" bash scripts/ci/check-all.sh || rc=$?
else
    echo "== 준비만: $(git log --oneline -1), harness.lock $(sed -n 's/^commit = //p' harness.lock | cut -c1-7)"
fi
after="$(config_hash)"
if [ "$before" != "$after" ]; then
    echo "하네스 카나리 실패: 공용 제품 .git/config가 바뀌었습니다($PRODUCT/.git/config). 바로 통합 담당이 확인하세요" >&2
    rc=1
fi
cd /
if [ "$rc" -eq 0 ]; then
    rm -rf -- "$RUN"
    echo "== 하네스 카나리 통과: ${CAND:0:7}${PREPARE:+ (준비만)}"
else
    echo "== 하네스 카나리 실패(rc=$rc): 사본을 남김 $RUN" >&2
fi
exit "$rc"

#!/usr/bin/env bash
# 하네스 카나리(Linux, MooKKo-Linux 안에서). PM 지시 2026-11-04(사용자 "그렇게해") ①: 하네스를 바꾸면 공용 제품 체크아웃이 아니라
# 따로 둔 사본에서 먼저 check-all을 한 번 돌린다. 통과한 판만 통합 담당이 harness.lock으로 공용에 올린다(영수증을 lock에 적고
# ci/check-harness-lock.py가 강제).
#
#   dev/harness-canary.sh <제품 본 체크아웃> <하네스 본 저장소> <후보 하네스 커밋> [기준 브랜치, 기본 foundation/engine] [--prepare-only]
#
# 공용 체크아웃과 같은 조건을 만든다(mookko-rust-qa 11-04 추가 8 ①): 공용에서는 Windows worktree라 check-all이 GIT_DIR·GIT_WORK_TREE를
# 내보낸다. 그래서 사본도 `git clone --shared` 위에 linked worktree를 하나 더 만들고, 그 worktree의 gitdir·작업 트리를 GIT_DIR·GIT_WORK_TREE로
# 내보낸 채 check-all을 돌린다(11-04 사고 ①: 표본 시험이 이 둘을 물려받아 공용 .git/config에 core.worktree를 씀).
# - 시작할 때 GIT_*·MOOKKO_* 환경을 모두 끊는다(우선순위만 CANARY_SLOT_PRIORITY, 기본 2).
# - 앞뒤로 견준다: 공용 제품 .git/config·HEAD, 사본 .git/config·HEAD, 사본 .git/worktrees/*/의 HEAD·gitdir·commondir·config*, 사본
#   브랜치 목록. 하나라도 바뀌면 실패(사본에서는 check-all이 git 설정·브랜치를 바꿀 일이 없으므로 정당한 변화가 없음).
# - 통과하면 영수증 줄을 낸다: `canary = <후보> base=<기준 판 커밋> at=<UTC 시각> result=pass`. 통합 담당이 제품 harness.lock에 그대로 붙인다.
# - 끝나면(TERM·INT·HUP 포함): 통과면 이 실행의 사본 폴더를 바로 지우고(WSL /tmp 자기 실행분 예외, CLAUDE.md), 실패면 남긴다.
#   남긴 실패 사본은 다음 카나리가 7일 지난 것만 지운다(보관 기한, 자기 접두어 폴더만).
# - 빌드 자리는 공용과 같은 자리를 쓴다(자리 막힘 같은 운영 사고는 카나리가 아니라 dev/build-slot-watch.py가 맡음).
# - --prepare-only: 사본을 만들고 맞추기까지만 하고 check-all은 돌리지 않는다(도구 자체 시험용, 영수증 없음).
set -euo pipefail

for v in $(compgen -e); do
    case "$v" in GIT_*|MOOKKO_*) unset "$v" ;; esac
done

if [ "$#" -lt 3 ]; then
    sed -n '6,6p' "$0" >&2
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
BASE_COMMIT="$(git -C "$PRODUCT" rev-parse --verify "$BASE^{commit}")"

ROOT="${TMPDIR:-/tmp}/mookko-test/harness-canary"
RUN="$ROOT/$(date +%Y%m%d%H%M%S)-$$"
mkdir -p "$RUN"
# 실패해서 남긴 사본의 보관 기한 7일(자기 접두어 폴더만)
find "$ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*-*' -mtime +7 -prune -exec rm -rf -- {} + 2>/dev/null || true

finish() {
    local status=$?
    cd /
    if [ "$status" -eq 0 ]; then
        rm -rf -- "$RUN"
    else
        echo "== 하네스 카나리 실패(rc=$status): 사본을 남김 $RUN(7일 뒤 다음 카나리가 지움)" >&2
    fi
}
trap finish EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
trap 'exit 129' HUP

echo "== 하네스 카나리: 후보 ${CAND:0:7}, 기준 $BASE(${BASE_COMMIT:0:7}), 사본 $RUN"
git clone -q --shared --branch "$BASE" "$PRODUCT" "$RUN/clone"
cd "$RUN/clone"
git config user.name "harness-canary"
git config user.email "canary@localhost"
[ "$BASE" = "foundation/engine" ] || git branch -q foundation/engine origin/foundation/engine
WT="$RUN/wt"
git worktree add -q -b canary/run "$WT" HEAD
WT_GITDIR="$(git -C "$WT" rev-parse --absolute-git-dir)"
cd "$WT"
sed -i "s/^commit = .*/commit = $CAND/" harness.lock
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

fingerprint() {
    sha256sum "$PRODUCT/.git/config" "$PRODUCT/.git/HEAD" "$RUN/clone/.git/config" "$RUN/clone/.git/HEAD"
    find "$RUN/clone/.git/worktrees" -maxdepth 2 -type f \( -name HEAD -o -name gitdir -o -name commondir -o -name 'config*' \) \
        | sort | xargs -r sha256sum
    git -C "$RUN/clone" for-each-ref --format='%(refname)' refs/heads | sort
}
before="$(fingerprint)"

check_status=0
if [ -z "$PREPARE" ]; then
    # 공용 Windows worktree와 같게: check-all이 Windows 분기에서 내보내는 두 값을 미리 내보냄
    GIT_DIR="$WT_GITDIR" GIT_WORK_TREE="$WT" MOOKKO_CANARY_RUN=1 MOOKKO_HARNESS_REPO="$HREPO" MOOKKO_SLOT_PRIORITY="${CANARY_SLOT_PRIORITY:-2}" \
        bash scripts/ci/check-all.sh || check_status=$?
else
    echo "== 준비만: $(git log --oneline -1), harness.lock $(sed -n 's/^commit = //p' harness.lock | cut -c1-7), GIT_DIR=$WT_GITDIR"
fi
after="$(fingerprint)"
if [ "$before" != "$after" ]; then
    echo "하네스 카나리 실패: git 메타데이터가 바뀌었습니다(공용 제품 .git 또는 사본 .git·worktrees)" >&2
    diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") >&2 || true
    exit 1
fi
if [ "$check_status" -ne 0 ]; then
    echo "하네스 카나리 실패: check-all rc=$check_status" >&2
    exit "$check_status"
fi
if [ -z "$PREPARE" ]; then
    echo "== 하네스 카나리 통과. 제품 harness.lock에 붙일 영수증:"
    echo "canary = $CAND base=$BASE_COMMIT at=$(date -u +%Y-%m-%dT%H:%M:%SZ) result=pass"
else
    echo "== 하네스 카나리 준비만 통과: ${CAND:0:7}"
fi
exit 0

#!/usr/bin/env bash
# WSL 멈춤 표지를 걸고 풉니다(Windows Git Bash). 표지가 paused인 동안 scripts/dev/wsl-run.sh는 WSL을 켜지 않습니다.
#   scripts/dev/wsl-pause.sh on "<사유>"   예: on "PM vhdx 압축"
#   scripts/dev/wsl-pause.sh off
#   scripts/dev/wsl-pause.sh status
# 압축 순서: (WSL 안) scripts/dev/build-slots.sh close → on → wsl --shutdown → 압축 → off. 경로는 scripts/dev/wsl.json.
# 표지 파일은 지우지 않고 첫 낱말(paused·running)만 바꿉니다.
set -euo pipefail

# 본 체크아웃 최상위(worktree는 <본 체크아웃>/.claude/worktrees/<이름> 아래, scripts/dev/machine.py와 같은 규칙).
main_root() {
    local root
    root="$(cd "$(dirname "$0")/../.." && pwd)"
    case "$root" in
        */.claude/worktrees/*) root="${root%%/.claude/worktrees/*}" ;;
    esac
    printf '%s\n' "$root"
}

SETTINGS="$(cd "$(dirname "$0")" && pwd)/wsl.json"
MARKER="$(sed -n 's/^[[:space:]]*"pauseMarker"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$SETTINGS")"
# 표지 경로는 본 체크아웃 기준 상대 경로입니다(기계 전용 절대 경로를 커밋하지 않음, PM 2026-11-03).
case "$MARKER" in
    /*|[A-Za-z]:*) ;;
    ?*) MARKER="$(main_root)/$MARKER" ;;
esac
if [ -z "$MARKER" ]; then
    echo "scripts/dev/wsl.json에서 pauseMarker를 읽지 못했습니다" >&2
    exit 2
fi

case "${1:-}" in
    on)
        if [ -z "${2:-}" ]; then
            echo "usage: $0 on \"<사유>\"" >&2
            exit 2
        fi
        mkdir -p "$(dirname "$MARKER")"
        printf 'paused %s %s\n' "$(date '+%F %T')" "$2" > "$MARKER"
        echo "멈춤 표지를 걸었습니다: $MARKER"
        ;;
    off)
        mkdir -p "$(dirname "$MARKER")"
        printf 'running %s\n' "$(date '+%F %T')" > "$MARKER"
        echo "멈춤 표지를 풀었습니다"
        ;;
    status)
        cat "$MARKER" 2>/dev/null || echo "running (표지 파일 없음)"
        ;;
    *)
        echo "usage: $0 on \"<사유>\"|off|status" >&2
        exit 2
        ;;
esac

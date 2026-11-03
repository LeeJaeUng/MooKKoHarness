#!/usr/bin/env bash
# Windows(Git Bash)에서 MooKKo-Linux로 명령을 넘깁니다. WSL을 부를 때는 wsl을 직접 쓰지 말고 이것을 씁니다.
#   dev/wsl-run.sh <리눅스 명령...>      예: dev/wsl-run.sh bash /mnt/<드라이브>/…/script.sh
# 명령은 wsl.exe --exec로 넘겨 Linux 기본 셸이 다시 읽지 않습니다(인자 그대로 실행).
# 설정은 config/dev/wsl.json(배포판 이름·멈춤 표지 경로). 표지 파일이 있으면 BOM·NUL·\r·공백을 뗀 첫 낱말이
# "running"일 때만 켭니다. 그 밖(paused, 빈 파일, 읽기 실패 등)은 WSL을 켜지 않고 75(EX_TEMPFAIL)로 끝납니다(QA 6b8bdab T1).
# 다시 시도하지 않습니다(재시도 고리가 내려간 WSL을 다시 켜서 압축이 깨짐).
set -euo pipefail

# 본 체크아웃 최상위(worktree는 <본 체크아웃>/.claude/worktrees/<이름> 아래, dev/machine.py와 같은 규칙).
main_root() {
    local root
    # 제품 저장소(표지는 제품 본 체크아웃의 data\에 둠). 제품의 얇은 래퍼가 MOOKKO_PRODUCT_ROOT를 넘깁니다.
    root="${MOOKKO_PRODUCT_ROOT:-$PWD}"
    root="$(cd "$root" && pwd)"
    case "$root" in
        */.claude/worktrees/*) root="${root%%/.claude/worktrees/*}" ;;
    esac
    printf '%s\n' "$root"
}

if [ "$#" -eq 0 ]; then
    echo "usage: $0 <linux command...>" >&2
    exit 2
fi

SETTINGS="$(cd "$(dirname "$0")/.." && pwd)/config/dev/wsl.json"
json_string() {
    sed -n "s/^[[:space:]]*\"$1\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" "$SETTINGS"
}
DISTRO="$(json_string distro)"
MARKER="$(json_string pauseMarker)"
# 표지 경로는 본 체크아웃 기준 상대 경로입니다(기계 전용 절대 경로를 커밋하지 않음, PM 2026-11-03).
case "$MARKER" in
    /*|[A-Za-z]:*) ;;
    ?*) MARKER="$(main_root)/$MARKER" ;;
esac
if [ -z "$DISTRO" ] || [ -z "$MARKER" ]; then
    echo "config/dev/wsl.json에서 distro·pauseMarker를 읽지 못했습니다" >&2
    exit 2
fi

if [ -e "$MARKER" ]; then
    state="$( { LC_ALL=C tr -d '\000\r' < "$MARKER" 2>/dev/null || true; } \
        | LC_ALL=C sed '1s/^\xEF\xBB\xBF//; 1s/^\xFF\xFE//; 1s/^\xFE\xFF//' | awk 'NR == 1 { print $1 }')"
    if [ "$state" != "running" ]; then
        echo "WSL 멈춤 표지가 running이 아니라 켜지 않습니다(첫 낱말 '${state}'): $MARKER" >&2
        echo "끝나면 PM이나 통합 담당이 dev/wsl-pause.sh off로 풉니다. 다시 시도하지 말고 기다리세요." >&2
        exit 75
    fi
fi

MSYS_NO_PATHCONV=1 exec wsl.exe -d "$DISTRO" --exec "$@"

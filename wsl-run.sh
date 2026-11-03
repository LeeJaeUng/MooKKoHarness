#!/usr/bin/env bash
# Windows(Git Bash)에서 MooKKo-Linux로 명령을 넘깁니다. WSL을 부를 때는 wsl을 직접 쓰지 말고 이것을 씁니다.
#   scripts/dev/wsl-run.sh <리눅스 명령...>      예: scripts/dev/wsl-run.sh bash /mnt/c/.../script.sh
# wsl.exe는 인자를 Linux 셸로 다시 읽어 $변수를 펼치므로, 변수·따옴표가 든 명령은 스크립트 파일로 넘깁니다.
# 설정은 scripts/dev/wsl.json(배포판 이름·멈춤 표지 경로). 멈춤 표지(scripts/dev/wsl-pause.sh on)가 있으면
# WSL을 켜지 않고 75(EX_TEMPFAIL)로 끝납니다. 다시 시도하지 않습니다(재시도 고리가 내려간 WSL을 다시 켜서 압축이 깨짐).
set -euo pipefail

if [ "$#" -eq 0 ]; then
    echo "usage: $0 <linux command...>" >&2
    exit 2
fi

SETTINGS="$(cd "$(dirname "$0")" && pwd)/wsl.json"
json_string() {
    sed -n "s/^[[:space:]]*\"$1\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" "$SETTINGS"
}
DISTRO="$(json_string distro)"
MARKER="$(json_string pauseMarker)"
if [ -z "$DISTRO" ] || [ -z "$MARKER" ]; then
    echo "scripts/dev/wsl.json에서 distro·pauseMarker를 읽지 못했습니다" >&2
    exit 2
fi

if [ -f "$MARKER" ] && [ "$(cut -d' ' -f1 "$MARKER" | head -n1)" = "paused" ]; then
    echo "WSL 멈춤 중이라 켜지 않습니다: $(cat "$MARKER")" >&2
    echo "끝나면 PM이나 통합 담당이 scripts/dev/wsl-pause.sh off로 풉니다. 다시 시도하지 말고 기다리세요." >&2
    exit 75
fi

MSYS_NO_PATHCONV=1 exec wsl.exe -d "$DISTRO" -- "$@"

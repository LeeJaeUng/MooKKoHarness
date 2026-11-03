#!/usr/bin/env bash
# 빌드 자리(config/dev/build-slots.json) 닫기·열기·상태(Linux, MooKKo-Linux 안에서).
#   dev/build-slots.sh status   자리마다 실제 잠금을 잡아 보고 비었는지, 누가 쥐었는지 봅니다(표지 파일을 믿지 않음).
#   dev/build-slots.sh close    모든 자리를 잡아 새 check-all이 시작하지 못하게 합니다. 돌던 빌드는 끝날 때까지 기다립니다.
#   dev/build-slots.sh open     close가 띄운 붙드는 프로세스를 끝내 자리를 엽니다.
# WSL 디스크 압축이나 업데이트 전에 close, 끝나면 open을 씁니다. wsl --shutdown이 붙드는 프로세스를 끝내면 자리는 저절로 열립니다.
# 상태 파일(<dir>/close-state)은 지우지 않고 덮어씁니다: "open", "closing <pid>", "closed <pid> <시각>".
set -euo pipefail

cd "$(dirname "$0")/.."  # 하네스 저장소 최상위
setting() {
    python3 -I -c 'import json,os,sys; v=json.load(open(sys.argv[1],encoding="utf-8"))[sys.argv[2]]; print(os.path.expanduser(v) if isinstance(v,str) else v)' config/dev/build-slots.json "$1"
}
DIR="$(setting dir)"
COUNT="$(setting count)"
WAIT_MINUTES="$(setting maxWaitMinutes)"
STATE="$DIR/close-state"
mkdir -p "$DIR"

holders_of() {
    local file="$1" p names=""
    for p in /proc/[0-9]*; do
        if ls -l "$p/fd" 2>/dev/null | grep -q -- "-> $file\$"; then
            names+="$(basename "$p")($(cat "$p/comm" 2>/dev/null)) "
        fi
    done
    printf '%s' "${names% }"
}

state_word() { cut -d' ' -f1 "$STATE" 2>/dev/null || echo open; }
state_pid() { cut -d' ' -f2 "$STATE" 2>/dev/null || true; }
holder_alive() {
    local pid
    pid="$(state_pid)"
    [ "$(state_word)" != "open" ] && [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

status() {
    local i file free=0
    for i in $(seq 1 "$COUNT"); do
        file="$DIR/slot-$i"
        touch "$file"
        if flock -n "$file" true; then
            echo "slot-$i: 비어 있음"
            free=$((free + 1))
        else
            echo "slot-$i: 잡힘 $(holders_of "$file")"
        fi
    done
    if holder_alive; then
        echo "close 상태: $(cat "$STATE")"
    elif [ "$(state_word)" != "open" ]; then
        echo "표지만 남음: '$(cat "$STATE")'의 프로세스가 없습니다(자리는 위 실제 잠금대로)"
    fi
    echo "free=$free/$COUNT"
}

close() {
    if holder_alive; then
        echo "이미 닫혀 있거나 닫는 중: $(cat "$STATE")"
        return
    fi
    # 자리를 모두 잡은 뒤 sleep으로 바뀌어 잠금을 계속 쥡니다(같은 프로세스 번호). 이 셸·세션과 떨어져 돌게 setsid로 띄웁니다.
    # 자리를 차례로 막고 기다리면 한 자리를 기다리는 동안 다른 자리를 새 check-all이 가져가므로(QA 6b8bdab T4), 빈 자리를
    # 1초마다 모두 엿봐 비는 대로 잡습니다. check-all은 close-state가 closing이면 새로 잡지 않습니다.
    setsid bash -c '
        dir="$1"; count="$2"; state="$3"
        declare -A held=()
        while [ "${#held[@]}" -lt "$count" ]; do
            for i in $(seq 1 "$count"); do
                [ -n "${held[$i]:-}" ] && continue
                exec {fd}>"$dir/slot-$i"
                if flock -n "$fd"; then
                    held[$i]="$fd"
                else
                    exec {fd}>&-
                fi
            done
            [ "${#held[@]}" -lt "$count" ] && sleep 1
        done
        printf "closed %s %s\n" "$$" "$(date "+%F %T")" > "$state"
        exec sleep infinity
    ' build-slots-close "$DIR" "$COUNT" "$STATE" </dev/null >/dev/null 2>&1 &
    local pid=$!
    printf 'closing %s\n' "$pid" > "$STATE"
    local deadline=$(( $(date +%s) + WAIT_MINUTES * 60 ))
    echo "== 돌던 빌드가 끝나기를 기다려 자리 $COUNT개를 잡습니다(최대 ${WAIT_MINUTES}분)"
    until [ "$(state_word)" = "closed" ]; do
        if ! kill -0 "$pid" 2>/dev/null; then
            printf 'open\n' > "$STATE"
            echo "자리를 붙드는 프로세스가 끝났습니다. 닫지 못했습니다." >&2
            exit 1
        fi
        if [ "$(date +%s)" -ge "$deadline" ]; then
            echo "자리를 ${WAIT_MINUTES}분 안에 다 잡지 못했습니다. 붙드는 프로세스($pid)는 계속 기다립니다. status로 보세요." >&2
            exit 1
        fi
        sleep 2
    done
    status
}

open() {
    if holder_alive; then
        kill "$(state_pid)"
        sleep 1
    else
        echo "close가 띄운 프로세스가 없습니다"
    fi
    printf 'open\n' > "$STATE"
    status
}

case "${1:-}" in
    status) status ;;
    close) close ;;
    open) open ;;
    *) echo "usage: $0 status|close|open" >&2; exit 2 ;;
esac

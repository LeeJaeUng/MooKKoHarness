# 빌드 자리 잡기(source해서 씀, 단독 실행 아님). ci/check-all.sh와 dev/with-build-slot.sh가 함께 씁니다.
# 부르는 쪽이 정함: H(하네스 루트), 현재 폴더 = 제품 worktree, MOOKKO_SLOT_RUNNER(대기표·옛 run 끄기에 쓰는 입구 이름).
# 끝나면 MOOKKO_BUILD_SLOT·CARGO_TARGET_DIR·CARGO_INCREMENTAL·CARGO_BUILD_JOBS가 잡히고, 자리 잠금(slot_fd)은 이 셸과 자식이
# 끝날 때 풀립니다. 이미 MOOKKO_BUILD_SLOT이 있으면(자리 안에서 다시 부름) 아무것도 하지 않습니다.
# 빌드 자리: 여러 세션이 동시에 돌리면 WSL 메모리가 모자라 연결이 끊깁니다(2026-10-30). config/dev/build-slots.json의
# 자리 수만큼만 동시에 돌고 나머지는 기다립니다. 잠금은 이 프로세스와 자식(시험용 DB 감싸기 포함)이 끝나면 풀립니다.
# 한 실행의 id(메모리 비상 기다림 30분을 실행 전체 몫으로 셈, mookko-rust-qa 추가 6 ⑥). 자식(시험 DB 감싸기·다시 부른 check-all)이 이어받습니다.
export MOOKKO_RUN_ID="${MOOKKO_RUN_ID:-$$-$(date +%s%N)}"
if [ -z "${MOOKKO_BUILD_SLOT:-}" ]; then
    slot_setting() {
        python3 -I -c 'import json,os,sys; v=json.load(open(sys.argv[1],encoding="utf-8"))[sys.argv[2]]; print(os.path.expanduser(v) if isinstance(v,str) else v)' "$H/config/dev/build-slots.json" "$1"
    }
    SLOT_DIR="$(slot_setting dir)"
    SLOT_COUNT="$(slot_setting count)"
    SLOT_POLL="$(slot_setting pollSeconds)"
    SLOT_DEADLINE=$(( $(date +%s) + $(slot_setting maxWaitMinutes) * 60 ))
    export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-$(slot_setting jobs)}"
    export MOOKKO_BASE_JOBS="$CARGO_BUILD_JOBS"
    mkdir -p "$SLOT_DIR"
    # dev/build-slots.sh close가 자리를 닫는 중이거나 닫았으면 새로 잡지 않습니다(QA 6b8bdab T4).
    slots_closing() {
        local word pid
        read -r word pid _ < "$SLOT_DIR/close-state" 2>/dev/null || return 1
        [ "$word" = "closing" ] || [ "$word" = "closed" ] || return 1
        [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
    }
    # 대기표(PM 2026-11-03: 자리는 우선순위 → 먼저 온 차례로, 기다리다 끊겨도 차례를 이어받음).
    # worktree마다 표 하나(<dir>/queue/<경로 해시>): "waiting|done 우선순위 줄선시각(ns) pid 경로". 우선순위는
    # MOOKKO_SLOT_PRIORITY(작을수록 앞, 기본 5; QA 높음 고침 1, 통합 담당 묶음 2). 같은 worktree가 다시 돌면 남은 waiting 표의
    # 줄선 시각을 그대로 써서 차례를 잃지 않습니다. 표 파일은 지우지 않고 덮어씁니다.
    QUEUE_DIR="$SLOT_DIR/queue"
    mkdir -p "$QUEUE_DIR"
    # 표는 worktree와 실행 입구마다 하나(check-all과 with-build-slot이 서로의 차례를 끄지 않게).
    ticket="$QUEUE_DIR/$(printf '%s%s' "$PWD" "${MOOKKO_SLOT_RUNNER:-ci/check-all.sh}" | sha1sum | cut -c1-16)"
    priority="${MOOKKO_SLOT_PRIORITY:-5}"
    enqueued="$(date +%s%N)"
    # 표가 아직 없으면(처음 도는 worktree·입구) 조용히 넘어갑니다: 2>/dev/null을 < 앞에 둬야 열기 실패 글이 숨겨집니다.
    if read -r t_state _ t_at t_pid _ 2>/dev/null < "$ticket" && [ "$t_state" = "waiting" ]; then
        enqueued="$t_at"
        # 같은 worktree의 옛 run이 아직 자리를 기다리면 끝냅니다. 같은 세션 것은 마지막 것만 남깁니다(사용자 2026-11-03
        # "빌드는 작업다하고 돌리는게 맞지 않아?", PM 전달). 자리를 잡은(done) run은 건드리지 않습니다.
        # pid가 다른 프로세스에 다시 쓰였을 수 있으므로, 같은 worktree에서 도는 check-all일 때만 끕니다.
        if [ -n "$t_pid" ] && [ "$t_pid" != "$$" ] && kill -0 "$t_pid" 2>/dev/null \
            && tr '\0' ' ' < "/proc/$t_pid/cmdline" 2>/dev/null | grep -qF "${MOOKKO_SLOT_RUNNER:-ci/check-all.sh}" \
            && [ "$(readlink "/proc/$t_pid/cwd" 2>/dev/null)" = "$PWD" ]; then
            echo "== 같은 worktree에서 자리를 기다리던 옛 run(pid $t_pid)을 끝내고 그 차례를 이어받습니다"
            kill -TERM "$t_pid" 2>/dev/null || true
        fi
    fi
    printf 'waiting %s %s %s %s\n' "$priority" "$enqueued" "$$" "$PWD" > "$ticket"
    # 살아 있는 waiting 표 가운데 이 표의 차례(0부터).
    queue_rank() {
        python3 -I - "$QUEUE_DIR" "$ticket" <<'PY'
import os, sys
from pathlib import Path
mine = Path(sys.argv[2]).name
live = []
for p in Path(sys.argv[1]).iterdir():
    try:
        state, prio, at, pid, *_ = p.read_text(encoding="utf-8").split()
        if state != "waiting":
            continue
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        continue
    live.append((int(prio), int(at), p.name))
live.sort()
print(next((i for i, (_, _, name) in enumerate(live) if name == mine), 0))
PY
    }
    announced=""
    while [ -z "${MOOKKO_BUILD_SLOT:-}" ]; do
        # PC 메모리 비상 관문(PM 11-04): Windows 전체 사용률이 emergency 이상이면 resume 아래까지 기다리고, 기한을 넘기면
        # 그대로 진행합니다(config/dev/memory-guard.json). 평소 몫은 WSL 상한과 자리 수(build-slots.json)로 묶습니다.
        # 메모리를 기다린 시간은 자리 기한(maxWaitMinutes)에서 뺍니다(mookko-rust-qa 추가 6 ⑥).
        memory_wait_start=$(date +%s)
        usable="$(python3 -X utf8 "$H/dev/memory-guard.py" slots "$SLOT_COUNT")"
        SLOT_DEADLINE=$(( SLOT_DEADLINE + $(date +%s) - memory_wait_start ))
        rank="$(queue_rank)"
        if ! slots_closing && [ "$rank" -lt "$usable" ]; then
            for i in $(seq 1 "$usable"); do
                exec {slot_fd}>"$SLOT_DIR/slot-$i"
                if flock -n "$slot_fd"; then
                    export MOOKKO_BUILD_SLOT="$i"
                    break
                fi
                exec {slot_fd}>&-
            done
        fi
        if [ -z "${MOOKKO_BUILD_SLOT:-}" ]; then
            if [ "$(date +%s)" -ge "$SLOT_DEADLINE" ]; then
                echo "build slot wait timed out: 빌드 자리를 기다리다 기한을 넘겼습니다($SLOT_DIR). 다시 돌리면 차례를 이어받습니다." >&2
                exit 1
            fi
            [ -z "$announced" ] && echo "== 빌드 자리 기다림(우선순위 $priority, 차례 $rank, 지금 쓸 수 있는 자리 ${usable}/${SLOT_COUNT}개)"
            announced=1
            sleep "$SLOT_POLL"
        fi
    done
    printf 'done %s %s %s %s\n' "$priority" "$enqueued" "$$" "$PWD" > "$ticket"
    # 빌드 캐시는 자리마다 하나(targetRoot/slot-<n>)를 worktree끼리 나눠 씁니다. 같은 자리는 위 잠금으로 한 번에 하나만 씁니다.
    # 세션마다 캐시를 따로 두니 8개·약 100GB까지 자라 C 드라이브가 바닥났습니다(2026-11-02). incremental은 캐시의 절반이고
    # check-all은 매번 전체를 보므로 끕니다.
    export CARGO_TARGET_DIR="$(slot_setting targetRoot)/slot-$MOOKKO_BUILD_SLOT"
    export CARGO_INCREMENTAL=0
    echo "== 빌드 자리 $MOOKKO_BUILD_SLOT/$SLOT_COUNT, CARGO_BUILD_JOBS=$CARGO_BUILD_JOBS, CARGO_TARGET_DIR=$CARGO_TARGET_DIR"
    # 같은 자리 캐시를 바로 전에 다른 worktree가 썼으면 workspace crate 결과만 지우고 다시 빌드합니다(registry 의존 결과는 둠).
    # cargo는 path crate 결과를 workspace 기준 상대 경로로 이름 짓고 파일 수정 시각으로 새것인지 보므로, 이 worktree 파일이
    # 더 오래됐으면 다른 worktree에서 만든 결과를 그대로 다시 씁니다(2026-11-02 운영툴 통합에서 옛 crate로 컴파일이 깨짐).
    mkdir -p "$CARGO_TARGET_DIR"
    slot_owner="$CARGO_TARGET_DIR/.mookko-worktree"
    if [ "$(cat "$slot_owner" 2>/dev/null || true)" != "$PWD" ]; then
        echo "== 빌드 자리 캐시를 다른 worktree가 썼음: workspace crate 결과를 지웁니다"
        mapfile -t members < <(cargo metadata --no-deps --format-version 1 --locked \
            | python3 -I -c 'import json,sys; [print(p["name"]) for p in json.load(sys.stdin)["packages"]]')
        # 목록이 비면 `cargo clean`이 자리 캐시 전체를 지우므로 멈춥니다(QA 2026-11-02 b1fb070 낮음).
        if [ "${#members[@]}" -eq 0 ]; then
            echo "workspace 패키지 목록이 비었습니다(cargo metadata). 자리 캐시를 지우지 않고 멈춥니다." >&2
            exit 1
        fi
        clean_args=()
        for name in "${members[@]}"; do clean_args+=(-p "$name"); done
        cargo clean --locked "${clean_args[@]}"
        # 공개 API 검사(nightly rustdoc)의 산출물도 버립니다. 남기면 다른 worktree의 옛 판 rmeta로 문서를 만들다
        # 실패하거나 거짓 통과합니다(2026-11-03 TOO_MANY_EVENTS unresolved import, 같은 판이 통과·실패를 오감).
        if [ -d "$CARGO_TARGET_DIR/public-api" ]; then
            cargo clean --target-dir "$CARGO_TARGET_DIR/public-api"
        fi
        cargo clean --doc
        printf '%s\n' "$PWD" > "$slot_owner"
    fi
fi


#!/usr/bin/env bash
# 커밋 전 전체 검사(Linux). 제품이 Linux에서 돌므로 검사도 Linux에서 합니다.
# 이 PC에서는 WSL 배포판 MooKKo-Linux에서 돌립니다(README › 검사).
set -euo pipefail
# git 기록·기준 판을 읽지 못하면 "건너뜀"이 아니라 실패(migration_lock 잠금 기록, vuln-register 기준 판 대조 ⑤). 보안 담당·QAManager
# 요청 2026-11-04. 표본 시험은 검사 폴더가 git 최상위가 아니라 대조 자체를 하지 않으므로 영향 없음.
export MOOKKO_REQUIRE_GIT_HISTORY="${MOOKKO_REQUIRE_GIT_HISTORY:-1}"

H="$(cd "$(dirname "$0")/.." && pwd)"  # 하네스 저장소 최상위
if [ -z "${MOOKKO_PRODUCT_ROOT:-}" ]; then
    echo "MOOKKO_PRODUCT_ROOT(검사할 제품 저장소)가 없습니다. 제품의 scripts/ci/check-all.sh(harness.lock 판)로 부르세요" >&2
    exit 2
fi
cd "$MOOKKO_PRODUCT_ROOT"

# 로그인 셸이 아니면 rustup이 PATH에 cargo를 넣지 않습니다(WSL에서 bash -c로 부를 때).
if ! command -v cargo >/dev/null 2>&1 && [ -f "$HOME/.cargo/env" ]; then
    . "$HOME/.cargo/env"
fi

# Windows에서 만든 worktree는 .git 파일이 C:/… 경로를 가리켜 WSL의 git이 읽지 못합니다(2026-11-03 links: 보안 관문
# git ls-files가 exit 128). 그 경로를 /mnt/<드라이브>/… 로 바꿔 GIT_DIR·GIT_WORK_TREE로 넘깁니다. 저장소 파일은 고치지 않습니다.
if [ -f .git ] && ! git rev-parse --git-dir >/dev/null 2>&1; then
    gitdir="$(sed -n 's/^gitdir: //p' .git | tr -d '\r')"
    case "$gitdir" in
        [A-Za-z]:/*)
            drive="$(printf '%s' "${gitdir%%:*}" | tr '[:upper:]' '[:lower:]')"
            export GIT_DIR="/mnt/$drive/${gitdir#?:/}"
            export GIT_WORK_TREE="$PWD"
            git rev-parse --git-dir >/dev/null
            echo "== Windows worktree: GIT_DIR=$GIT_DIR"
            ;;
    esac
fi

# 빌드 자리: 여러 세션이 동시에 돌리면 WSL 메모리가 모자라 연결이 끊깁니다(2026-10-30). config/dev/build-slots.json의
# 자리 수만큼만 동시에 돌고 나머지는 기다립니다. 잠금은 이 프로세스와 자식(시험용 DB 감싸기 포함)이 끝나면 풀립니다.
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
    ticket="$QUEUE_DIR/$(printf '%s' "$PWD" | sha1sum | cut -c1-16)"
    priority="${MOOKKO_SLOT_PRIORITY:-5}"
    enqueued="$(date +%s%N)"
    if read -r t_state _ t_at t_pid _ < "$ticket" 2>/dev/null && [ "$t_state" = "waiting" ]; then
        enqueued="$t_at"
        # 같은 worktree의 옛 run이 아직 자리를 기다리면 끝냅니다. 같은 세션 것은 마지막 것만 남깁니다(사용자 2026-11-03
        # "빌드는 작업다하고 돌리는게 맞지 않아?", PM 전달). 자리를 잡은(done) run은 건드리지 않습니다.
        # pid가 다른 프로세스에 다시 쓰였을 수 있으므로, 같은 worktree에서 도는 check-all일 때만 끕니다.
        if [ -n "$t_pid" ] && [ "$t_pid" != "$$" ] && kill -0 "$t_pid" 2>/dev/null \
            && tr '\0' ' ' < "/proc/$t_pid/cmdline" 2>/dev/null | grep -q "ci/check-all.sh" \
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
        # PC 메모리 관문(사용자 2026-11-03 "램 90%이하로 만 먹어야해"): Windows 전체 사용률이 hard 이상이면 내려갈 때까지
        # 기다리고, soft 이상이면 자리를 1개만 씁니다(config/dev/memory-guard.json).
        usable="$(python3 -X utf8 "$H/dev/memory-guard.py" slots "$SLOT_COUNT")"
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

# 자기 캐시가 폴더 한도를 넘으면 자기 것만 지우고 새로 빌드하고, 여유가 모자라면 24시간 넘은 남의 캐시부터 지우고, 그래도 모자라면 빌드를 시작하지 않습니다
# (2026-10-30 C 드라이브 0 사고 뒤, dev/disk-guard.py).
if [ -z "${MOOKKO_DISK_GUARD_DONE:-}" ]; then
    python3 -X utf8 "$H/dev/disk-guard.py"
    export MOOKKO_DISK_GUARD_DONE=1
fi

# 저장소 어댑터 시험은 실제 PostgreSQL에 붙습니다. 접속 설정(MOOKKO_TEST_POSTGRES)이 없으면
# Podman으로 시험용 PostgreSQL을 잠깐 띄우고 그 안에서 이 검사를 다시 실행합니다(끝나면 지움).
if [ -z "${MOOKKO_TEST_POSTGRES:-}" ]; then
    exec "$H/dev/with-test-postgres.sh" "$H/ci/check-all.sh" "$@"
fi
export MOOKKO_REQUIRE_TEST_POSTGRES=1

# 빌드 중에는 메모리 사용률을 30초마다 기록하고 soft 이상이면 WSL page cache를 비웁니다. 끝날 때 최고값을 남깁니다.
python3 -X utf8 "$H/dev/memory-guard.py" watch &
MEMORY_WATCH=$!
trap 'kill "$MEMORY_WATCH" 2>/dev/null || true; wait "$MEMORY_WATCH" 2>/dev/null || true' EXIT

# 단계마다 시작 전에 메모리를 봅니다: hard 이상이면 내려갈 때까지 기다리고, soft 이상이면 cargo 작업 수를 줄입니다.
run() {
    CARGO_BUILD_JOBS="$(python3 -X utf8 "$H/dev/memory-guard.py" step "$1" "${MOOKKO_BASE_JOBS:-$CARGO_BUILD_JOBS}")"
    export CARGO_BUILD_JOBS
    echo "== $* (jobs $CARGO_BUILD_JOBS)"
    "$@"
}

run cargo fmt --all -- --check
run cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
run cargo test --workspace --all-features --locked
run cargo deny --locked check
run cargo audit --deny warnings
run "$H/ci/check-security-tools.sh"
run "$H/ci/check-public-api.sh"
run python3 -X utf8 "$H/ci/check-forbid-unsafe.py" "$PWD"
run python3 -X utf8 "$H/ci/check-boundaries.py" "$PWD"
run python3 -X utf8 "$H/ci/check-no-hardcoded-endpoints.py" "$PWD"
run python3 -X utf8 "$H/ci/check-stack.py" "$PWD"
run python3 -X utf8 "$H/ci/check-lint-escapes.py" "$PWD"
run python3 -X utf8 "$H/ci/check-test-tempdirs.py" "$PWD"
run python3 -X utf8 "$H/ci/check-dev-exposure.py" "$PWD"
run python3 -X utf8 "$H/ci/check-containers.py" "$PWD"
run python3 -X utf8 "$H/ci/check-file-size.py" "$PWD"
run python3 -X utf8 "$H/ci/check-engine-reuse.py" "$PWD"
# 하네스 정본과 제품 사본(관문·규약·스킬)이 같은지, 하네스 폴더 자리(둘 다 처음에는 경고, PM 2026-11-03).
run python3 -X utf8 "$H/ci/check-harness-copies.py" --warn "$PWD" "$H"
run python3 -X utf8 "$H/ci/check-folder-layout.py" --warn "$H"
run python3 -X utf8 "$H/ci/test_ci_checks.py"
run python3 -X utf8 "$H/ci/check-acceptance.py" "$PWD"
run python3 -X utf8 "$H/ci/check-design-sources.py" "$PWD"
run python3 -X utf8 "$H/ci/check-hardcoded-values.py" "$PWD"
run python3 -X utf8 "$H/ci/check-test-time.py" "$PWD"
run python3 -X utf8 "$H/ci/check-prr.py" "$PWD"
run python3 -X utf8 "$H/ci/check-production-config.py" "$PWD"
run python3 -X utf8 "$H/ci/check-waivers.py" "$PWD"
run python3 -X utf8 "$H/ci/check-vuln-register.py" "$PWD"
run python3 -X utf8 "$H/ci/check-systemd-units.py" "$PWD"
run "$H/ci/db/check-db.sh"
echo "== all checks passed"

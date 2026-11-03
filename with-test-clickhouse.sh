#!/usr/bin/env bash
# 시험용 ClickHouse를 Podman(rootless)으로 잠깐 띄우고 명령을 실행한 뒤 지웁니다(with-test-postgres.sh와 같은 방식).
#   scripts/dev/with-test-clickhouse.sh <명령...>
# 이미지·주소 같은 설정은 scripts/dev/test-clickhouse.json에서만 읽습니다(코드에 두지 않음).
# 명령에는 MOOKKO_TEST_CLICKHOUSE(접속 JSON 경로)와 MOOKKO_REQUIRE_TEST_CLICKHOUSE=1을 넘깁니다.
# 접속 JSON의 칸은 로그 담당 ClickHouse 어댑터 설정의 connection 모양(host·port·tls·user·passwordFile·database …)을 따릅니다.
# 데이터는 컨테이너 tmpfs에만 두고, 임시 파일은 ${TMPDIR:-/tmp}/mookko-test/mookko/<실행 번호>/ 아래에 둡니다. 명령이 성공하면
# 이 실행이 만든 그 폴더만 바로 지우고, 실패하면 원인 확인용으로 남깁니다(CLAUDE.md › WSL 시험 임시 폴더 예외, 2026-11-02).
set -euo pipefail

if [ "$#" -eq 0 ]; then
    echo "usage: $0 <command...>" >&2
    exit 2
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SETTINGS="$ROOT/scripts/dev/test-clickhouse.json"
RUN_ID="ch-$(date +%Y%m%d%H%M%S)-$$"
TEST_ROOT="${TMPDIR:-/tmp}/mookko-test/mookko"
RUN_DIR="$TEST_ROOT/$RUN_ID"
RUN_DIR_MADE=""
NAME="mookko-test-$RUN_ID"

setting() {
    python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$SETTINGS" "$1"
}

cleanup() {
    local status=$?
    podman rm -f -t 2 "$NAME" >/dev/null 2>&1 || true
    # 지우는 것은 이 실행이 mkdir로 직접 만든 RUN_DIR 하나뿐입니다(남이 만든 폴더·그 밖의 경로는 건드리지 않음).
    if [ -z "$RUN_DIR_MADE" ]; then
        return
    fi
    if [ "$status" -ne 0 ]; then
        echo "FAILED (exit $status): test folder kept for diagnosis: $RUN_DIR" >&2
        return
    fi
    rm -rf -- "$RUN_DIR"
}
trap cleanup EXIT

mkdir -p "$TEST_ROOT"
mkdir -m 700 "$RUN_DIR"
RUN_DIR_MADE=1
python3 -I -c 'import secrets; print(secrets.token_hex(24))' > "$RUN_DIR/password"
chmod 600 "$RUN_DIR/password"
PASSWORD="$(cat "$RUN_DIR/password")"

IMAGE="$(setting image)"
BIND_HOST="$(setting bindHost)"
CONTAINER_PORT="$(setting containerHttpPort)"
DATABASE="$(setting database)"
USER_NAME="$(setting user)"
TMPFS_SIZE="$(setting tmpfsSize)"
READY_TIMEOUT="$(setting readyTimeoutSeconds)"

# 암호는 환경 변수 파일로만 넘깁니다(명령줄·프로세스 목록에 남지 않게).
printf 'CLICKHOUSE_DB=%s\nCLICKHOUSE_USER=%s\nCLICKHOUSE_PASSWORD=%s\nCLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1\n' \
    "$DATABASE" "$USER_NAME" "$PASSWORD" > "$RUN_DIR/env"
chmod 600 "$RUN_DIR/env"

podman run -d --rm --name "$NAME" \
    --env-file "$RUN_DIR/env" \
    --tmpfs "/var/lib/clickhouse:rw,size=$TMPFS_SIZE" \
    -p "$BIND_HOST::$CONTAINER_PORT" \
    "$IMAGE" >/dev/null

HOST_PORT="$(podman port "$NAME" "$CONTAINER_PORT/tcp" | head -n1 | sed 's/.*://')"

# 실제로 쓰는 HTTP 인터페이스로 질의가 될 때까지 기다립니다(네이티브 포트가 먼저 열려도 HTTP는 조금 늦을 수 있음).
http_ready() {
    python3 -I - "$BIND_HOST" "$HOST_PORT" "$USER_NAME" "$RUN_DIR/password" <<'PY'
import base64, sys, urllib.request
host, port, user, pw_file = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
token = base64.b64encode(f"{user}:{open(pw_file).read().strip()}".encode()).decode()
req = urllib.request.Request(f"http://{host}:{port}/", data=b"SELECT 1", headers={"Authorization": f"Basic {token}"})
try:
    with urllib.request.urlopen(req, timeout=2) as r:
        sys.exit(0 if r.read().strip() == b"1" else 1)
except Exception:
    sys.exit(1)
PY
}
deadline=$((SECONDS + READY_TIMEOUT))
until http_ready; do
    if [ "$SECONDS" -ge "$deadline" ]; then
        echo "test clickhouse did not become ready in ${READY_TIMEOUT}s" >&2
        podman logs "$NAME" >&2 || true
        exit 1
    fi
    sleep 0.5
done

python3 -I - "$SETTINGS" "$RUN_DIR" "$HOST_PORT" <<'PY'
import json, sys
settings_path, run_dir, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
s = json.load(open(settings_path))
config = {
    "host": s["bindHost"],
    "port": port,
    "user": s["user"],
    "passwordFile": f"{run_dir}/password",
    "database": s["database"],
    **s["connection"],
}
json.dump(config, open(f"{run_dir}/clickhouse.json", "w"), indent=2)
PY

echo "== test clickhouse ready ($IMAGE, http port $HOST_PORT)"
export MOOKKO_TEST_CLICKHOUSE="$RUN_DIR/clickhouse.json"
export MOOKKO_REQUIRE_TEST_CLICKHOUSE=1
"$@"

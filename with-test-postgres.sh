#!/usr/bin/env bash
# 시험용 PostgreSQL을 Podman(rootless)으로 잠깐 띄우고 명령을 실행한 뒤 지웁니다.
#   scripts/dev/with-test-postgres.sh <명령...>
# 이미지·주소 같은 설정은 scripts/dev/test-postgres.json에서만 읽습니다(코드에 두지 않음).
# 명령에는 MOOKKO_TEST_POSTGRES(접속 JSON 경로)와 MOOKKO_REQUIRE_TEST_POSTGRES=1을 넘깁니다.
# 데이터는 컨테이너 tmpfs에만 두고, 임시 파일은 ${TMPDIR:-/tmp}/mookko-test/mookko/<실행 번호>/ 아래에 두었다가 바로 지웁니다.
set -euo pipefail

if [ "$#" -eq 0 ]; then
    echo "usage: $0 <command...>" >&2
    exit 2
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SETTINGS="$ROOT/scripts/dev/test-postgres.json"
RUN_ID="pg-$(date +%Y%m%d%H%M%S)-$$"
RUN_DIR="${TMPDIR:-/tmp}/mookko-test/mookko/$RUN_ID"
NAME="mookko-test-$RUN_ID"

setting() {
    python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$SETTINGS" "$1"
}

cleanup() {
    podman rm -f -t 2 "$NAME" >/dev/null 2>&1 || true
    rm -rf "$RUN_DIR"
}
trap cleanup EXIT

mkdir -p "$RUN_DIR"
chmod 700 "$RUN_DIR"
python3 -I -c 'import secrets; print(secrets.token_hex(24))' > "$RUN_DIR/password"
chmod 600 "$RUN_DIR/password"

IMAGE="$(setting image)"
BIND_HOST="$(setting bindHost)"
CONTAINER_PORT="$(setting containerPort)"
DATABASE="$(setting database)"
USER_NAME="$(setting user)"
TMPFS_SIZE="$(setting tmpfsSize)"
READY_TIMEOUT="$(setting readyTimeoutSeconds)"

podman run -d --rm --name "$NAME" \
    -e POSTGRES_DB="$DATABASE" -e POSTGRES_USER="$USER_NAME" \
    -e POSTGRES_PASSWORD_FILE=/run/mookko/password \
    -v "$RUN_DIR/password:/run/mookko/password:ro,Z" \
    --tmpfs "/var/lib/postgresql:rw,size=$TMPFS_SIZE" \
    -p "$BIND_HOST::$CONTAINER_PORT" \
    "$IMAGE" -c fsync=off -c synchronous_commit=off -c full_page_writes=off -c max_connections=300 >/dev/null

# 초기화(임시 서버)가 끝나고 실제 서버가 받을 때까지 기다립니다. 컨테이너 안 유닉스 소켓으로 확인합니다.
deadline=$((SECONDS + READY_TIMEOUT))
until podman exec "$NAME" psql -U "$USER_NAME" -d "$DATABASE" -tAc 'SELECT 1' >/dev/null 2>&1 \
    && podman logs "$NAME" 2>&1 | grep -q 'PostgreSQL init process complete'; do
    if [ "$SECONDS" -ge "$deadline" ]; then
        echo "test postgres did not become ready in ${READY_TIMEOUT}s" >&2
        podman logs "$NAME" >&2 || true
        exit 1
    fi
    sleep 0.5
done

HOST_PORT="$(podman port "$NAME" "$CONTAINER_PORT/tcp" | head -n1 | sed 's/.*://')"

python3 -I - "$SETTINGS" "$RUN_DIR" "$HOST_PORT" <<'PY'
import json, sys
settings_path, run_dir, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
s = json.load(open(settings_path))
config = {
    "host": s["bindHost"],
    "port": port,
    "database": s["database"],
    "user": s["user"],
    "passwordFile": f"{run_dir}/password",
    **s["connection"],
}
json.dump(config, open(f"{run_dir}/postgres.json", "w"), indent=2)
PY

echo "== test postgres ready ($IMAGE, port $HOST_PORT)"
export MOOKKO_TEST_POSTGRES="$RUN_DIR/postgres.json"
export MOOKKO_REQUIRE_TEST_POSTGRES=1
"$@"

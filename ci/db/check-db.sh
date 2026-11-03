#!/usr/bin/env bash
# DB 검사 묶음(docs/policy/conventions/sql.md). check-all.sh가 부릅니다.
# 1) 검사 도구의 표본 시험(T-PY-7) 2) 이관 글 검사 3) 설계서 등급 검사 4) 실제 PostgreSQL 적용 시험.
# 실제 적용은 MOOKKO_TEST_POSTGRES(scripts/dev/with-test-postgres.sh)가 있어야 하고, check-all은 늘 그 안에서 돕니다.
set -euo pipefail

cd "$(dirname "$0")/../../.."
# 검사가 저장소 안에 __pycache__를 남기지 않게 합니다(임시 파일 규칙).
export PYTHONDONTWRITEBYTECODE=1

run() {
    echo "== $*"
    "$@"
}

run python3 -X utf8 scripts/ci/db/test_db_checks.py
run python3 -X utf8 scripts/ci/db/migration_lint.py
run python3 -X utf8 scripts/ci/db/data_classes.py
run python3 -X utf8 scripts/ci/db/migration_apply.py

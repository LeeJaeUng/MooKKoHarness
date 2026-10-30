"""이관 실제 적용 시험 (docs/policy/conventions/sql.md S-MIG-8·S-MIG-3·S-BND-2·S-MONEY-2, database.md §2·§7).

글로 읽는 검사(migration_lint.py)가 놓치는 것 — 문법 오류, 트랜잭션 안의 CONCURRENTLY, 계정·주인, 실제로 생긴 형식, 막기 함수 — 를
시험용 PostgreSQL(scripts/dev/with-test-postgres.sh, 접속 JSON은 MOOKKO_TEST_POSTGRES)에서 엔진 이관기와 같은 길로 확인한다.
서비스 `migrations/` 폴더마다:
1. DB 준비 스크립트처럼 새 DB와 계정을 만든다: 주인 `<스키마>_owner`(로그인 없음), 이관 `_migrate`(주인의 구성원), `_app`·`_ro`·`_recon`·`_maint`.
   스키마는 `AUTHORIZATION <스키마>_owner`(database.md §2.2, engine.md 이관 단계).
2. 이관 계정으로 파일을 차례대로 적용한다(엔진 `SchemaMigrator`와 같게): `__SCHEMA__`는 스키마 이름으로, 비어 있지 않은 첫 줄이
   `-- mookko:transaction off`면 트랜잭션 밖 한 문장, 아니면 한 트랜잭션에서 `SET LOCAL ROLE <주인>` → `search_path` → `lock_timeout`.
3. 엔진 `grant`처럼 권한을 맞춘 뒤(덧붙이기만 표는 이름 규칙으로 고름 — 서비스가 `append_only`로 지정했는지는 [QA]) 목록(catalog)으로 본다:
   기본 키, 금지 형식, enum, 기본 파티션, 잘못된 색인, 앱 계정 권한(스키마 CREATE·TRUNCATE·TRIGGER·REFERENCES·덧붙이기만 표의
   UPDATE·DELETE), PUBLIC 권한, 덧붙이기만 표의 막기 트리거(기본 ENABLE만 켜진 것으로 셈)와 그것이 실제로 거부하는지
   (UPDATE·DELETE는 같은 모양 임시 표에 같은 트리거를 붙여 해 보고, TRUNCATE는 원래 표에 해 봄), 객체 주인.
4. DB와 계정을 지운다(시험 컨테이너 안, 파일 아님).
접속 설정이 없으면 "건너뜀(통과 아님)"을 출력하고, MOOKKO_REQUIRE_TEST_POSTGRES=1이면 실패한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sqltext  # noqa: E402
from migration_lint import ROOT, default_schema, first_nonempty_line, migration_dirs  # noqa: E402
from pgwire import Connection, PgError, quote_ident, quote_literal  # noqa: E402

APPEND_ONLY = "ledger|journal|audit"
HEAD = "_heads?$"  # 사슬·구간 머리는 지금 상태 표(migration_lint.APPEND_ONLY와 같음)
ROLE_SUFFIXES = ("owner", "migrate", "app", "ro", "recon", "maint")
OUTSIDE_TRANSACTION = "-- mookko:transaction off"  # 엔진 migrate.rs와 같은 표시
LOCK_TIMEOUT_MS = 3000  # 엔진 MigrateSettings 기본값
TIMEOUT_SECONDS = 30.0
FORBIDDEN_TYPES = (
    "'real', 'double precision', 'numeric', 'money', 'json', 'timestamp without time zone', "
    "'time with time zone', 'character varying'"
)


@dataclass(frozen=True)
class Target:
    """적용할 이관 폴더 하나."""

    directory: Path
    rel: str
    schema: str


def load_config() -> dict | None:
    path = os.environ.get("MOOKKO_TEST_POSTGRES")
    if not path:
        return None
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("tls", {}).get("mode") != "disable":
        raise SystemExit("migration_apply: 시험 접속은 tls.mode = disable(같은 장비의 시험 컨테이너)만 지원")
    config["password"] = Path(config["passwordFile"]).read_text(encoding="utf-8").strip()
    return config


def connect(config: dict, user: str, password: str, database: str) -> Connection:
    return Connection.connect(config["host"], int(config["port"]), user, password, database, TIMEOUT_SECONDS)


def targets(root: Path) -> list[Target]:
    out: list[Target] = []
    for directory in migration_dirs(root):
        rel = directory.relative_to(root)
        if any("clickhouse" in p for p in rel.parts):
            continue
        schema = default_schema(rel)
        for path in sorted(directory.glob("*.sql")):
            override = sqltext.split(path.read_text(encoding="utf-8")).directives.get("schema")
            if override:
                schema = override[0]
                break
        if schema:
            out.append(Target(directory, rel.as_posix(), schema))
    return out


def bootstrap(admin: Connection, database: str, schema: str, password: str) -> None:
    """DB 준비 스크립트가 하는 일(database.md §2.2): 주인 역할(로그인 없음), 이관 계정(주인 역할의 구성원), 앱·읽기 계정."""
    for suffix in ROLE_SUFFIXES:
        role = quote_ident(f"{schema}_{suffix}")
        login = f"LOGIN PASSWORD {quote_literal(password)}" if suffix == "migrate" else "NOLOGIN"
        admin.query(f"CREATE ROLE {role} {login} NOSUPERUSER NOCREATEDB NOCREATEROLE")
    admin.query(f"GRANT {quote_ident(schema + '_owner')} TO {quote_ident(schema + '_migrate')}")
    admin.query(f"CREATE DATABASE {quote_ident(database)}")
    admin.query(f"REVOKE ALL ON DATABASE {quote_ident(database)} FROM PUBLIC")
    roles = ", ".join(quote_ident(f"{schema}_{s}") for s in ROLE_SUFFIXES)
    admin.query(f"GRANT CONNECT ON DATABASE {quote_ident(database)} TO {roles}")


def bootstrap_schema(db_admin: Connection, schema: str) -> None:
    db_admin.query(
        f"REVOKE ALL ON SCHEMA public FROM PUBLIC;\n"
        f"CREATE SCHEMA {quote_ident(schema)} AUTHORIZATION {quote_ident(schema + '_owner')};"
    )


def apply_files(conn: Connection, target: Target, problems: list[str]) -> int:
    """엔진 `SchemaMigrator`와 같은 길: 비어 있지 않은 첫 줄이 `-- mookko:transaction off`면 트랜잭션 밖 한 문장,
    아니면 트랜잭션 안에서 `SET LOCAL ROLE <주인>` → `search_path` → `lock_timeout` → 문장(migrate.rs, engine.md §저장소)."""
    applied = 0
    owner = quote_ident(f"{target.schema}_owner")
    for path in sorted(target.directory.glob("*.sql")):
        text = path.read_text(encoding="utf-8").replace("__SCHEMA__", quote_ident(target.schema))
        rel = f"{target.rel}/{path.name}"
        try:
            if first_nonempty_line(text) == OUTSIDE_TRANSACTION:
                conn.query(text)
            else:
                conn.query(
                    f"BEGIN;\nSET LOCAL ROLE {owner};\nSET LOCAL search_path = {quote_ident(target.schema)}, pg_catalog;\n"
                    f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_MS}ms';\n{text}\n;COMMIT;"
                )
            applied += 1
        except PgError as error:
            problems.append(f"{rel}: S-MIG-8 적용 실패 {error.sqlstate} {error.message}")
            try:
                conn.query("ROLLBACK")
            except PgError:
                pass  # 이미 트랜잭션 밖(transaction off 파일)
            break
    return applied


def grant_like_engine(db: Connection, target: Target) -> None:
    """엔진 `SchemaMigrator::grant`와 같은 권한: 앱 계정은 표마다 DML만, 덧붙이기만 표는 SELECT·INSERT만, 읽기 계정은 SELECT.
    덧붙이기만 표는 서비스가 `append_only`로 지정한 것이라 SQL에서 알 수 없으므로 이름 규칙(S-MONEY-2)으로 고른다 —
    서비스가 실제로 지정했는지는 [QA]."""
    schema = quote_ident(target.schema)
    app = quote_ident(f"{target.schema}_app")
    reader = quote_ident(f"{target.schema}_ro")
    sql = [f"REVOKE ALL ON SCHEMA {schema} FROM PUBLIC;", f"GRANT USAGE ON SCHEMA {schema} TO {app}, {reader};"]
    for (name,) in db.query(f"SELECT tablename FROM pg_tables WHERE schemaname = {quote_literal(target.schema)} ORDER BY 1").rows:
        table = f"{schema}.{quote_ident(name or '')}"
        allowed = "SELECT, INSERT" if re.search(APPEND_ONLY, name or "") and not re.search(HEAD, name or "") else "SELECT, INSERT, UPDATE, DELETE"
        sql += [f"REVOKE ALL ON {table} FROM {app};", f"GRANT {allowed} ON {table} TO {app};", f"GRANT SELECT ON {table} TO {reader};"]
    db.query(f"SET ROLE {quote_ident(target.schema + '_owner')};\n" + "\n".join(sql) + "\nRESET ROLE;")


def probe_row_change(db: Connection, schema: str, table: str, event: str) -> str | None:
    """덧붙이기만 표의 UPDATE·DELETE를 실제로 해 본다. 원래 표에 넣을 행은 제약 때문에 만들 수 없으므로, 열만 같은 임시 표
    (`CREATE TEMP TABLE … AS … WITH NO DATA` — NOT NULL·CHECK가 없음)에 원래 표의 켜진 UPDATE·DELETE 트리거를 같은 함수로
    붙이고, 빈 행 하나를 넣은 뒤 바꿔 본다. 거부되면 통과, 바뀌면 문제. 모두 한 트랜잭션 안에서 하고 되돌린다."""
    qualified = f"{quote_ident(schema)}.{quote_ident(table)}"
    try:
        db.query("BEGIN")
        db.query(f"CREATE TEMP TABLE dbcheck_probe ON COMMIT DROP AS SELECT * FROM {qualified} WITH NO DATA")
        definitions = db.query(
            f"SELECT pg_get_triggerdef(t.oid) FROM pg_trigger t WHERE t.tgrelid = {quote_literal(qualified)}::regclass "
            f"AND NOT t.tgisinternal AND t.tgenabled = 'O' AND t.tgtype & (8 | 16) <> 0"
        ).rows
        for (definition,) in definitions:
            moved = re.sub(r"\bON\s+\S+\s+FOR\s+EACH\b", "ON pg_temp.dbcheck_probe FOR EACH", definition or "", count=1)
            db.query(moved)
        db.query("INSERT INTO pg_temp.dbcheck_probe DEFAULT VALUES")
        column = db.query(
            "SELECT attname FROM pg_attribute WHERE attrelid = 'pg_temp.dbcheck_probe'::regclass AND attnum > 0 AND NOT attisdropped ORDER BY attnum LIMIT 1"
        ).rows[0][0]
        statement = (
            f"UPDATE pg_temp.dbcheck_probe SET {quote_ident(column or '')} = {quote_ident(column or '')}"
            if event == "UPDATE"
            else "DELETE FROM pg_temp.dbcheck_probe"
        )
    except PgError as error:
        db.query("ROLLBACK")
        return f"{event} 시험을 준비하지 못함 {error.sqlstate} {error.message}"
    try:
        db.query(statement)
    except PgError:
        db.query("ROLLBACK")
        return None  # 막기 트리거가 거부함(기대한 결과)
    db.query("ROLLBACK")
    return f"{event}가 막히지 않음(막기 트리거 함수가 거부하지 않음)"


def catalog_checks(db: Connection, target: Target, problems: list[str]) -> None:
    s = quote_literal(target.schema)
    app = quote_literal(f"{target.schema}_app")
    where = target.rel

    def rows(sql: str) -> list[list[str | None]]:
        return db.query(sql).rows

    for (name,) in rows(
        f"SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = {s} AND c.relkind IN ('r', 'p') AND NOT c.relispartition "
        f"AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'p') ORDER BY 1"
    ):
        problems.append(f"{where}: S-MIG-3 `{name}`에 기본 키가 없음")
    for table, column, kind, length in rows(
        f"SELECT table_name, column_name, data_type, character_maximum_length::text FROM information_schema.columns "
        f"WHERE table_schema = {s} AND (data_type IN ({FORBIDDEN_TYPES}) "
        f"OR (data_type = 'character' AND character_maximum_length <> 3)) ORDER BY 1, 2"
    ):
        problems.append(f"{where}: S-TYPE `{table}.{column}` 형식 `{kind}{'(' + length + ')' if length else ''}` 금지")
    for (name,) in rows(f"SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = {s} AND t.typtype = 'e'"):
        problems.append(f"{where}: S-TYPE-4 enum `{name}` 금지")
    for (name,) in rows(
        f"SELECT c.relname FROM pg_partitioned_table p JOIN pg_class c ON c.oid = p.partrelid "
        f"JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = {s} AND p.partdefid <> 0"
    ):
        problems.append(f"{where}: S-PART-2 `{name}`에 기본(DEFAULT) 파티션")
    for (name,) in rows(
        f"SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = {s} AND NOT i.indisvalid AND c.relkind = 'i'"
    ):
        problems.append(f"{where}: S-MIG-6 잘못된(INVALID) 색인 `{name}` — CONCURRENTLY 실패 뒤 남은 것")
    if rows(f"SELECT 1 WHERE has_schema_privilege({app}, {s}, 'CREATE')"):
        problems.append(f"{where}: S-BND-2 앱 계정이 스키마에 CREATE(DDL) 권한을 가짐")
    for name, privilege in rows(
        f"SELECT c.relname, p.privilege FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, "
        f"unnest(ARRAY['TRUNCATE', 'TRIGGER', 'REFERENCES', 'UPDATE', 'DELETE']) AS p(privilege) "
        f"WHERE n.nspname = {s} AND c.relkind IN ('r', 'p') AND has_table_privilege({app}, c.oid, p.privilege) "
        f"AND (p.privilege IN ('TRUNCATE', 'TRIGGER', 'REFERENCES') OR (c.relname ~ '{APPEND_ONLY}' AND c.relname !~ '{HEAD}')) ORDER BY 1, 2"
    ):
        rule = "S-MONEY-2" if privilege in ("UPDATE", "DELETE") else "S-BND-2"
        problems.append(f"{where}: {rule} 앱 계정이 `{name}`에 {privilege} 권한을 가짐")
    for (name,) in rows(
        f"SELECT DISTINCT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(c.relacl) a "
        f"WHERE n.nspname = {s} AND a.grantee = 0 ORDER BY 1"
    ):
        problems.append(f"{where}: S-BND-5 `{name}`에 PUBLIC 권한")
    append_only = rows(
        f"SELECT c.relname, "
        f"bool_or(t.tgtype & 16 <> 0), bool_or(t.tgtype & 8 <> 0), bool_or(t.tgtype & 32 <> 0) "
        f"FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"LEFT JOIN pg_trigger t ON t.tgrelid = c.oid AND NOT t.tgisinternal AND t.tgenabled = 'O' "
        f"WHERE n.nspname = {s} AND c.relkind IN ('r', 'p') AND NOT c.relispartition AND c.relname ~ '{APPEND_ONLY}' AND c.relname !~ '{HEAD}' "
        f"GROUP BY c.relname ORDER BY 1"
    )
    for name, has_update, has_delete, has_truncate in append_only:
        missing = [e for e, ok in (("UPDATE", has_update), ("DELETE", has_delete), ("TRUNCATE", has_truncate)) if ok != "t"]
        if missing:
            problems.append(f"{where}: S-MONEY-2 덧붙이기만 하는 `{name}`에 막기 트리거 없음: {', '.join(missing)}")
            continue
        for event in ("UPDATE", "DELETE"):
            problem = probe_row_change(db, target.schema, name or "", event)
            if problem:
                problems.append(f"{where}: S-MONEY-2 `{name}` {problem}")
        try:
            db.query(f"BEGIN; TRUNCATE {quote_ident(target.schema)}.{quote_ident(name or '')};")
            problems.append(f"{where}: S-MONEY-2 `{name}` TRUNCATE가 막히지 않음")
        except PgError as error:
            # 시험 계정은 초사용자라 권한 문제가 아니라 트리거가 거부한 것이어야 함(사용자 정의 오류 코드는 그대로 둠).
            if error.sqlstate.startswith(("42P", "0A")):
                problems.append(f"{where}: S-MONEY-2 `{name}` TRUNCATE가 트리거가 아닌 이유로 실패 {error.sqlstate} {error.message}")
        db.query("ROLLBACK")
    owner = quote_literal(f"{target.schema}_owner")
    for name, kind, actual in rows(
        f"SELECT c.relname, c.relkind::text, pg_get_userbyid(c.relowner) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = {s} AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f') AND pg_get_userbyid(c.relowner) <> {owner} ORDER BY 1"
    ):
        problems.append(f"{where}: S-BND-2 `{name}`({kind})의 주인이 `{actual}` — 주인 역할 `{target.schema}_owner`(SET LOCAL ROLE)로 만듦")


def run_target(config: dict, target: Target) -> list[str]:
    problems: list[str] = []
    run = f"{os.getpid()}_{secrets.token_hex(3)}"
    database = f"mookko_dbcheck_{target.schema}_{run}"[:63]
    password = secrets.token_hex(16)
    with connect(config, config["user"], config["password"], config["database"]) as admin:
        try:
            bootstrap(admin, database, target.schema, password)
            with connect(config, config["user"], config["password"], database) as db_admin:
                bootstrap_schema(db_admin, target.schema)
            with connect(config, f"{target.schema}_migrate", password, database) as migrate:
                applied = apply_files(migrate, target, problems)
            with connect(config, config["user"], config["password"], database) as db_admin:
                grant_like_engine(db_admin, target)
                catalog_checks(db_admin, target, problems)
            print(f"  {target.rel}: 스키마 {target.schema}, 이관 {applied}개 적용")
        finally:
            admin.query(f"DROP DATABASE IF EXISTS {quote_ident(database)} WITH (FORCE)")
            for suffix in ROLE_SUFFIXES:
                admin.query(f"DROP ROLE IF EXISTS {quote_ident(f'{target.schema}_{suffix}')}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="검사할 저장소 뿌리(시험용)")
    args = parser.parse_args(argv)
    config = load_config()
    if config is None:
        if os.environ.get("MOOKKO_REQUIRE_TEST_POSTGRES") == "1":
            print("migration apply failed: MOOKKO_TEST_POSTGRES가 없음(scripts/dev/with-test-postgres.sh 안에서 실행)")
            return 1
        print("migration apply 건너뜀(통과 아님): MOOKKO_TEST_POSTGRES가 없음")
        return 0
    found = targets(args.root.resolve())
    problems: list[str] = []
    for target in found:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", target.schema):
            problems.append(f"{target.rel}: S-TYPE-6 스키마 이름 `{target.schema}`")
            continue
        problems += run_target(config, target)
    if problems:
        print(f"migration apply failed ({len(problems)}):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"migration apply passed ({len(found)} dirs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

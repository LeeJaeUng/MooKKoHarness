"""이관 실제 적용 시험 (docs/policy/conventions/sql.md S-MIG-8·S-MIG-3·S-BND-2·S-MONEY-2, database.md §2·§7).

글로 읽는 검사(migration_lint.py)가 놓치는 것 — 문법 오류, 트랜잭션 안의 CONCURRENTLY, 계정·주인, 실제로 생긴 형식, 막기 함수 — 를
시험용 PostgreSQL(dev/with-test-postgres.sh, 접속 JSON은 MOOKKO_TEST_POSTGRES)에서 엔진 이관기와 같은 길로 확인한다.
서비스 `migrations/` 폴더마다:
1. DB 준비 스크립트처럼 새 DB와 계정을 만든다: 주인 `<스키마>_owner`(로그인 없음), 이관 `_migrate`(주인의 구성원), `_app`·`_ro`·`_recon`·`_maint`.
   스키마는 `AUTHORIZATION <스키마>_owner`(database.md §2.2, engine.md 이관 단계).
2. `crates/apps/mookko-<서비스>`에 이관 설정 예시가 있으면 그 실행 파일의 **엔진 이관 단계**(`migrate`)를 실제로 돌린다(이관 적용·
   grant·grant_recon·파티션 만들기를 엔진이 함, 3의 흉내는 건너뜀). 실행 파일이 없는 표본만 아래처럼 흉내 낸다.
   이관 계정으로 파일을 차례대로 적용한다(엔진 `SchemaMigrator`와 같게): `__SCHEMA__`는 스키마 이름으로, 머리(맨 앞 `--` 줄) 안에
   `-- mookko:transaction off`가 있으면 트랜잭션 밖 한 문장, 아니면 한 트랜잭션에서 `SET LOCAL ROLE <주인>` → `search_path` → `lock_timeout`.
3. 엔진 `grant`처럼 권한을 맞춘 뒤(파티션 자식은 권한 없음, 읽기 계정은 서비스 코드의 `READER_HIDDEN`·`READER_COLUMNS`대로, 덧붙이기만 표는
   이름 규칙으로 고름 — 서비스가 `append_only`로 지정했는지는 [QA]) 목록(catalog)으로 본다:
   기본 키, 금지 형식, enum, 기본 파티션, 잘못된 색인, 앱 계정 권한(스키마 CREATE·TRUNCATE·TRIGGER·REFERENCES·덧붙이기만 표의
   UPDATE·DELETE), PUBLIC 권한, 덧붙이기만 표의 막기 트리거(기본 ENABLE만 켜진 것으로 셈)와 그것이 실제로 거부하는지
   (UPDATE·DELETE는 같은 모양 임시 표에 같은 트리거를 붙여 해 보고, TRUNCATE는 원래 표에 해 봄), 객체 주인,
   읽기 계정이 설계서 등급 `개인` 이상 열을 읽지 못하는지(S-SEC-9).
4. DB와 계정을 지운다(시험 컨테이너 안, 파일 아님).
접속 설정이 없으면 "건너뜀(통과 아님)"을 출력하고, MOOKKO_REQUIRE_TEST_POSTGRES=1이면 실패한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_classes  # noqa: E402
import pending  # noqa: E402
import sqltext  # noqa: E402
from migration_lint import ROOT, default_schema, is_key_dir, migration_dirs, outside_transaction, owning_service  # noqa: E402
from pgwire import Connection, PgError, quote_ident, quote_literal  # noqa: E402

APPEND_ONLY = "ledger|journal|audit"
HEAD = "_heads?$"  # 사슬·구간 머리는 지금 상태 표(migration_lint.APPEND_ONLY와 같음)
ROLE_SUFFIXES = ("owner", "migrate", "app", "ro", "recon", "maint")
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
    service: str


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
        service = owning_service(rel)
        schema = default_schema(rel)
        for path in sorted(directory.glob("*.sql")):
            override = sqltext.split(path.read_text(encoding="utf-8")).directives.get("schema")
            if override:
                schema = override[0]
                break
        if schema:
            out.append(Target(directory, rel.as_posix(), schema, service or schema))
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


def bootstrap_schema(db_admin: Connection, schema: str, extra: tuple[str, ...] = ()) -> None:
    """서비스 스키마(와 엔진 공유 스키마 `sharedStores.schema`)를 주인 역할 소유로 만든다(DB 준비 단계가 하는 일)."""
    owner = quote_ident(schema + '_owner')
    sql = ["REVOKE ALL ON SCHEMA public FROM PUBLIC;"] + [f"CREATE SCHEMA {quote_ident(n)} AUTHORIZATION {owner};" for n in (schema, *extra)]
    db_admin.query("\n".join(sql))


def apply_files(conn: Connection, target: Target, problems: list[str]) -> int:
    """엔진 `SchemaMigrator`와 같은 길: 머리(맨 앞에 이어지는 `--` 줄) 안에 `-- mookko:transaction off`가 있으면 트랜잭션 밖 한 문장,
    아니면 트랜잭션 안에서 `SET LOCAL ROLE <주인>` → `search_path` → `lock_timeout` → 문장(migrate.rs, engine.md §저장소)."""
    applied = 0
    owner = quote_ident(f"{target.schema}_owner")
    for path in sorted(target.directory.glob("*.sql")):
        text = path.read_text(encoding="utf-8").replace("__SCHEMA__", quote_ident(target.schema))
        rel = f"{target.rel}/{path.name}"
        try:
            if outside_transaction(text):
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


def grant_like_engine(db: Connection, target: Target, reader_access: data_classes.ReaderAccess) -> None:
    """엔진 `SchemaMigrator::grant`(access.rs, E-DB-12)와 같은 권한: 보통 표와 파티션 부모만 받고 파티션 자식은 모두 걷어 냄.
    앱 계정은 DML만, 덧붙이기만 표는 SELECT·INSERT만. 읽기 계정은 닫힌 기본(엔진 9f027fa) — `reader_all_tables()`·`READER_TABLES`로 연 표만
    SELECT, 서비스 코드의 `READER_HIDDEN` 표는 없음, `READER_COLUMNS` 표는 그 열만. 덧붙이기만 표는 서비스가 `append_only`로 지정한 것이라 SQL에서 알 수 없으므로 이름 규칙(S-MONEY-2)으로
    고른다 — 서비스가 실제로 지정했는지는 [QA]. 표마다 좁히는 `table_privileges`는 덧붙이기만 판정에 영향이 없어 따라 하지 않는다."""
    schema = quote_ident(target.schema)
    app = quote_ident(f"{target.schema}_app")
    reader = quote_ident(f"{target.schema}_ro")
    key_db = is_key_dir(Path(target.rel))
    sql = [f"REVOKE ALL ON SCHEMA {schema} FROM PUBLIC;", f"GRANT USAGE ON SCHEMA {schema} TO {app}" + ("" if key_db else f", {reader}") + ";"]
    tables = db.query(
        f"SELECT c.relname, c.relispartition::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = {quote_literal(target.schema)} AND c.relkind IN ('r', 'p') ORDER BY 1"
    ).rows
    for name, child in tables:
        name = name or ""
        table = f"{schema}.{quote_ident(name)}"
        sql += [f"REVOKE ALL ON {table} FROM {app};", f"REVOKE ALL ON {table} FROM {reader};"]
        if child == "true":
            continue
        if key_db:
            sql.append(f"GRANT SELECT, INSERT, DELETE ON {table} TO {app};")  # 키는 바꾸지 않음(§9.8)
            continue
        allowed = "SELECT, INSERT" if re.search(APPEND_ONLY, name) and not re.search(HEAD, name) else "SELECT, INSERT, UPDATE, DELETE"
        sql.append(f"GRANT {allowed} ON {table} TO {app};")
        if name in reader_access.hidden:
            continue
        if name in reader_access.columns:
            columns = ", ".join(quote_ident(c) for c in reader_access.columns[name])
            sql.append(f"GRANT SELECT ({columns}) ON {table} TO {reader};")
        elif reader_access.all_tables or name in reader_access.tables:
            sql.append(f"GRANT SELECT ON {table} TO {reader};")
        # 그 밖의 표는 읽기 계정이 못 봄(엔진 닫힌 기본, 9f027fa)
    db.query(f"SET ROLE {quote_ident(target.schema + '_owner')};\n" + "\n".join(sql) + "\nRESET ROLE;")


def grant_recon_like_engine(db: Connection, target: Target, reader_access: data_classes.ReaderAccess) -> None:
    """엔진 `SchemaMigrator::grant_recon`(recon.rs, E-DB-15)과 같은 권한: 대사 계정(`_recon`)은 스키마 `USAGE`와 서비스 코드
    `RECON_VIEWS` 보기의 `SELECT`만. 표·다른 보기·시퀀스 권한은 모두 걷어 냄. 키 DB(§9.8)에는 대사 계정이 없음."""
    if is_key_dir(Path(target.rel)):
        return
    schema = quote_ident(target.schema)
    recon = quote_ident(f"{target.schema}_recon")
    sql = [f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {schema} FROM {recon};", f"GRANT USAGE ON SCHEMA {schema} TO {recon};"]
    relations = db.query(
        f"SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = {quote_literal(target.schema)} AND c.relkind IN ('r', 'p', 'v', 'm', 'f') ORDER BY 1"
    ).rows
    for (name,) in relations:
        relation = f"{schema}.{quote_ident(name or '')}"
        sql.append(f"REVOKE ALL ON {relation} FROM {recon};")
        if name in reader_access.recon_views:
            sql.append(f"GRANT SELECT ON {relation} TO {recon};")
    db.query(f"SET ROLE {quote_ident(target.schema + '_owner')};\n" + "\n".join(sql) + "\nRESET ROLE;")


def recon_checks(
    db: Connection,
    target: Target,
    classified: dict[str, dict[str, str]],
    reader_access: data_classes.ReaderAccess,
    problems: list[str],
) -> None:
    """S-SEC-9 대사 계정: 보기가 쓰는 원본 열(`information_schema.view_column_usage`, WHERE·JOIN에 쓴 것도)에 설계서 등급 `개인`
    이상이 없어야 하고, 대사 계정은 원본 표를 읽지 못하고 정한 보기만 읽어야 한다(`has_table_privilege`)."""
    s = quote_literal(target.schema)
    recon = quote_literal(f"{target.schema}_recon")
    for view in sorted(reader_access.recon_views):
        used = db.query(
            f"SELECT table_name, column_name FROM information_schema.view_column_usage "
            f"WHERE view_schema = {s} AND view_name = {quote_literal(view)} AND table_schema = {s} ORDER BY 1, 2"
        ).rows
        for table, column in used:
            known = classified.get(table or "", {})
            grade = known.get(column or "", known.get(data_classes.REST))
            if grade is not None and data_classes.RANK.get(grade, 0) >= data_classes.RANK["개인"]:
                problems.append(f"{target.rel}: S-SEC-9 대사 보기 `{view}`가 `{table}.{column}`(등급 `{grade}`)을 씀")
    readable = db.query(
        f"SELECT c.relname, c.relkind::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = {s} AND c.relkind IN ('r', 'p', 'v', 'm', 'f') AND has_table_privilege({recon}, c.oid, 'SELECT') ORDER BY 1"
    ).rows
    for name, kind in readable:
        if name not in reader_access.recon_views:
            what = "원본 표" if kind in ("r", "p") else "정하지 않은 보기"
            problems.append(f"{target.rel}: S-SEC-9 대사 계정이 {what} `{name}`을 읽을 수 있음")


def reader_checks(
    db: Connection,
    target: Target,
    classified: dict[str, dict[str, str]],
    reader_access: data_classes.ReaderAccess,
    waivers: list[pending.Pending],
    problems: list[str],
) -> None:
    """S-SEC-9: 권한을 맞춘 뒤 읽기 계정(`_ro`)이 설계서 등급 `개인` 이상 열을 읽을 수 없어야 한다(`has_column_privilege`).
    `(나머지)`가 `개인` 이상이면 등급 표에 따로 적지 않은 열 모두가 대상. pending.json에 S-SEC-9로 기한 안에 오른 서비스는 경고만."""
    s = quote_literal(target.schema)
    reader = quote_literal(f"{target.schema}_ro")
    readable = db.query(
        f"SELECT c.relname, a.attname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped "
        f"WHERE n.nspname = {s} AND c.relkind IN ('r', 'p') AND NOT c.relispartition "
        f"AND has_column_privilege({reader}, c.oid, a.attnum, 'SELECT') ORDER BY 1, 2"
    ).rows
    by_table: dict[str, set[str]] = {}
    for table, column in readable:
        by_table.setdefault(table or "", set()).add(column or "")
    # 코드 설정과 실제 권한이 같은지(QA 795bf8c 낮음: 글자 확인만이 아니라 grant 뒤 권한을 본다).
    for table in sorted(reader_access.hidden):
        if by_table.get(table):
            problems.append(f"{target.rel}: S-SEC-9 감춘 표 `{table}`을 읽기 계정이 읽을 수 있음: {', '.join(sorted(by_table[table]))}")
        if db.query(f"SELECT 1 WHERE has_table_privilege({reader}, {quote_literal(target.schema + '.' + table)}, 'SELECT')").rows:
            problems.append(f"{target.rel}: S-SEC-9 감춘 표 `{table}`에 읽기 계정의 표 SELECT 권한이 있음")
    for table, columns in sorted(reader_access.columns.items()):
        if by_table.get(table, set()) != set(columns):
            problems.append(f"{target.rel}: S-SEC-9 `{table}` 읽기 계정 열이 설정과 다름: 설정 {sorted(columns)}, 실제 {sorted(by_table.get(table, set()))}")
    for table, column in readable:
        known = classified.get(table or "", {})
        grade = known.get(column or "", known.get(data_classes.REST))
        if grade is not None and data_classes.RANK.get(grade, 0) >= data_classes.RANK["개인"]:
            message = f"{target.rel}: S-SEC-9 읽기 계정이 `{table}.{column}`(등급 `{grade}`)을 읽을 수 있음"
            item = pending.match(waivers, target.rel, "S-SEC-9")
            if pending.is_waived(item):
                print(f"  유예({item.owner}, {item.until} 까지): {message}")
            else:
                problems.append(message)


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


# 엔진 키 ID 모양(1~32자, `[A-Za-z0-9_-]`)을 지키는 CHECK. 정의 글에서 공백·괄호·`::text`를 뺀 것이 `CHECK<열>_bidx_kid` + 이 글과 같아야 함.
KID_CHECK = "~'^[A-Za-z0-9_-]{1,32}$'"
# CHECK 정의를 맞춰 보기 좋게 고친 글: 공백·괄호·`::text`를 뺌(PostgreSQL이 괄호를 더 붙여 돌려주므로). 정의 전체를 같음(=)으로 봄.
CHECK_TEXT = r"regexp_replace(replace(pg_get_constraintdef(x.oid), '::text', ''), '[\s()]', '', 'g')"


def blind_index_checks(rows, s: str, where: str, problems: list[str]) -> None:
    """`<열>_bidx`가 엔진 `BlindIndex::compute`의 `{key_id, digest}` 모양을 담는지 본다(S-SEC-3, E-DB-7): 값은 `bytea` 32바이트
    CHECK와 그 열로 시작하는 색인(같은 값 찾기·유일), 키 ID는 `<열>_bidx_kid text`(`CHECK (<열>_bidx_kid ~ '^[A-Za-z0-9_-]{1,32}$')`)이고 두 열이 같이 차거나 같이 빔."""
    for table, column, kind, not_null, kid_kind, kid_not_null, has_len, has_index, has_pair, has_kid_shape in rows(
        rf"SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, "
        rf"format_type(k.atttypid, k.atttypmod), k.attnotnull, "
        rf"EXISTS (SELECT 1 FROM pg_constraint x WHERE x.conrelid = c.oid AND x.contype = 'c' "
        rf"AND {CHECK_TEXT} = 'CHECKoctet_length' || a.attname || '=32'), "
        rf"EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.oid AND i.indkey[0] = a.attnum), "
        rf"EXISTS (SELECT 1 FROM pg_constraint x WHERE x.conrelid = c.oid AND x.contype = 'c' "
        rf"AND {CHECK_TEXT} = 'CHECK' || a.attname || 'ISNULL=' || a.attname || '_kidISNULL'), "
        rf"EXISTS (SELECT 1 FROM pg_constraint x WHERE x.conrelid = c.oid AND x.contype = 'c' "
        rf"AND {CHECK_TEXT} = 'CHECK' || a.attname || '_kid' || {quote_literal(KID_CHECK)}) "
        rf"FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        rf"JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped AND a.attname ~ '_bidx$' "
        rf"LEFT JOIN pg_attribute k ON k.attrelid = c.oid AND k.attname = a.attname || '_kid' AND NOT k.attisdropped "
        rf"WHERE n.nspname = {s} AND c.relkind IN ('r', 'p') AND NOT c.relispartition ORDER BY 1, 2"
    ):
        name = f"`{table}.{column}`"
        if kind != "bytea":
            problems.append(f"{where}: S-SEC-3 {name} 형식 `{kind}` — blind index는 `bytea`")
        if has_len != "t":
            problems.append(f"{where}: S-SEC-3 {name}에 `CHECK (octet_length({column}) = 32)`(이 글 그대로 따로 된 CHECK)가 없음")
        if has_index != "t":
            problems.append(f"{where}: S-SEC-3 {name}으로 시작하는 색인(UNIQUE 또는 찾기용)이 없음")
        if kid_kind is None:
            problems.append(f"{where}: S-SEC-3 {name} 옆에 키 ID 열 `{column}_kid text`가 없음(엔진 `KeyedHash.key_id`)")
            continue
        if kid_kind != "text":
            problems.append(f"{where}: S-SEC-3 `{table}.{column}_kid` 형식 `{kid_kind}` — `text`")
        if has_kid_shape != "t":
            problems.append(f"{where}: S-SEC-3 `{table}.{column}_kid`에 `CHECK ({column}_kid ~ '^[A-Za-z0-9_-]{{1,32}}$')`가 없음(엔진 키 ID 모양)")
        if not_null != kid_not_null:
            problems.append(f"{where}: S-SEC-3 {name}와 `{column}_kid`의 NOT NULL이 다름 — 같이 차거나 같이 빔")
        elif not_null != "t" and has_pair != "t":
            problems.append(f"{where}: S-SEC-3 {name}와 `{column}_kid`가 NULL을 받는데 같이 비게 하는 CHECK가 없음")


def key_db_checks(db: Connection, target: Target, problems: list[str]) -> None:
    """키 DB(§9.8, S-SEC-10)를 실제 DB에서 본다: 앱 계정은 키 표에 SELECT·INSERT·DELETE만(UPDATE·TRUNCATE·TRIGGER·REFERENCES 없음),
    읽기·대사 계정은 스키마도 못 봄, 키 표의 기본 키는 `(subject_id, purpose)`, 표·색인·시퀀스 말고 다른 것(보기·함수 등)은 없음."""
    s = quote_literal(target.schema)
    app = quote_literal(f"{target.schema}_app")
    where = target.rel
    for name, privilege in db.query(
        f"SELECT c.relname, p.privilege FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, "
        f"unnest(ARRAY['UPDATE', 'TRUNCATE', 'TRIGGER', 'REFERENCES']) AS p(privilege) "
        f"WHERE n.nspname = {s} AND c.relkind IN ('r', 'p') AND has_table_privilege({app}, c.oid, p.privilege) ORDER BY 1, 2"
    ).rows:
        problems.append(f"{where}: S-SEC-10 키 DB 앱 계정이 `{name}`에 {privilege} 권한을 가짐(SELECT·INSERT·DELETE만)")
    for suffix in ("ro", "recon", "maint"):
        role = f"{target.schema}_{suffix}"
        if db.query(f"SELECT 1 FROM pg_roles WHERE rolname = {quote_literal(role)} AND has_schema_privilege(rolname, {s}, 'USAGE')").rows:
            problems.append(f"{where}: S-SEC-10 키 DB에 `{role}`이 스키마 USAGE를 가짐 — 키 DB에는 읽기·대사·유지보수 계정이 없음")
    for name, columns in db.query(
        f"SELECT c.relname, (SELECT string_agg(a.attname, ',' ORDER BY a.attname) FROM pg_constraint k "
        f"JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(k.conkey) WHERE k.conrelid = c.oid AND k.contype = 'p') "
        f"FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = {s} AND c.relkind IN ('r', 'p') AND NOT c.relispartition AND c.relname <> 'schema_migrations' ORDER BY 1"
    ).rows:
        if columns != "purpose,subject_id":
            problems.append(f"{where}: S-SEC-10 키 표 `{name}`의 기본 키가 `(subject_id, purpose)`가 아님(지금 `{columns or '없음'}`)")
    for name, kind in db.query(
        f"SELECT c.relname, c.relkind::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = {s} AND c.relkind NOT IN ('r', 'p', 'i', 'I', 'S') AND c.relname <> 'schema_migrations' "
        f"UNION ALL SELECT p.proname, 'function' FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = {s} ORDER BY 1"
    ).rows:
        problems.append(f"{where}: S-SEC-10 키 DB에 표가 아닌 `{name}`({kind}) — 키 DB에는 키 표만")


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
    blind_index_checks(rows, s, where, problems)
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


ENGINE_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class EngineApp:
    """서비스 실행 파일과 그 이관 설정 예시(엔진 이관 단계를 실제로 돌릴 때)."""

    exe: Path
    example: dict


def migrate_example(root: Path, service: str) -> Path:
    name = f"mookko-{service}"
    return root / "crates" / "apps" / name / "config" / f"{name}.migrate.example.json"


def engine_app(root: Path, target: Target) -> EngineApp | None:
    """`crates/apps/mookko-<서비스>`에 이관 설정 예시가 있으면 그 실행 파일로 엔진 이관 단계(`migrate`)를 돌린다(QA cd3ba1c 낮음:
    파이썬 grant 흉내는 엔진 grant와 다른 점을 못 잡음). 실행 파일은 `cargo test`가 이미 만든 것을 쓰고, 없으면 그것만 만든다.
    표본 저장소(실행 파일 없음)는 None — 엔진을 흉내 내는 길로 본다. 키 DB 폴더는 None: 실행 파일이 있으면 서비스 DB와 같은
    `migrate` 실행에서 키 DB(`keyDatabases`, E-DB-17)도 돌리므로 따로 돌리지 않는다(`main`이 건너뜀)."""
    if is_key_dir(Path(target.rel)):
        return None
    name = f"mookko-{target.service}"
    example = migrate_example(root, target.service)
    if not example.is_file():
        return None
    target_dir = Path(os.environ.get("CARGO_TARGET_DIR") or root / "target")
    exe = target_dir / "debug" / name
    if not exe.is_file():
        subprocess.run(["cargo", "build", "--locked", "-p", name, "--bin", name], cwd=root, check=True, timeout=ENGINE_TIMEOUT_SECONDS)
    return EngineApp(exe, json.loads(example.read_text(encoding="utf-8")))


def engine_settings(
    example: dict, config: dict, database: str, key_database: str | None, secret: Path, access: data_classes.ReaderAccess
) -> dict:
    """이관 설정 예시에서 접속만 시험 DB로 바꾼 설정. 키 DB(`keyDatabases.<서비스>`, E-DB-17)는 따로 된 시험 DB(`key_database`)와
    이관 계정 `<서비스>_keys_migrate`로 바꾼다(키 클러스터는 서비스 DB와 다른 클러스터라 같은 DB에 두지 않음)."""
    settings = json.loads(json.dumps(example))
    settings["migrate"]["telemetry"] = {"filter": "warn", "format": "json"}
    test_connection = {"host": config["host"], "port": int(config["port"]), "passwordFile": str(secret), "tls": {"mode": "disable"}}
    for name, db in settings["migrate"]["databases"].items():
        db["connection"].update({**test_connection, "database": database, "user": f"{name}_migrate"})
        if access.recon_views:
            db["reconRole"] = f"{name}_recon"
    for name, db in (settings["migrate"].get("keyDatabases") or {}).items():
        if key_database is None:
            raise ValueError(f"keyDatabases.{name}가 있는데 키 시험 DB가 없음")
        db["connection"].update({**test_connection, "database": key_database, "user": f"{name}_keys_migrate"})
    return settings


def engine_migrate(
    config: dict, target: Target, app: EngineApp, database: str, key_database: str | None, password: str,
    access: data_classes.ReaderAccess, problems: list[str],
) -> bool:
    """이관 설정 예시의 접속만 시험 DB로 바꿔 `<실행 파일> migrate --config`를 돌린다. 임시 설정·암호 파일은 시험 DB 감싸기
    (`dev/with-test-postgres.sh`)의 실행 폴더 안에 두어, 감싸기가 끝날 때 함께 치운다."""
    work = Path(os.environ["MOOKKO_TEST_POSTGRES"]).resolve().parent / f"dbcheck-{database}"
    work.mkdir(mode=0o700)
    secret = work / "migrate-password.txt"
    secret.write_text(password, encoding="utf-8")
    secret.chmod(0o600)
    settings = engine_settings(app.example, config, database, key_database, secret, access)
    path = work / "migrate.json"
    path.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
    done = subprocess.run([str(app.exe), "migrate", "--config", str(path)], capture_output=True, text=True, timeout=ENGINE_TIMEOUT_SECONDS)
    if done.returncode != 0:
        tail = " | ".join((done.stderr or done.stdout).strip().splitlines()[-5:])
        problems.append(f"{target.rel}: S-MIG-8 엔진 이관 단계 실패(exit {done.returncode}): {tail}")
        return False
    return True


def partition_checks(db: Connection, target: Target, problems: list[str]) -> None:
    """엔진 이관 단계가 끝난 뒤 파티션 부모마다 달 파티션이 실제로 있어야 한다(S-PART-3 — 서비스 코드가 `partitioned`로 적지
    않았으면 아무도 만들지 않음). 정적 검사(lint `lint_partitioned`)가 글 모양을 놓쳐도 여기서 잡는다."""
    for (name,) in db.query(
        f"SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = {quote_literal(target.schema)} "
        f"AND c.relkind = 'p' AND NOT c.relispartition AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhparent = c.oid) ORDER BY 1"
    ).rows:
        problems.append(f"{target.rel}: S-PART-3 엔진 이관 단계 뒤 `{name}`에 달 파티션이 없음 — 서비스 코드가 엔진 `partitioned`로 적지 않음")


def shared_reader_checks(db: Connection, target: Target, schema: str, root: Path, problems: list[str]) -> None:
    """엔진 공유 스키마(`sharedStores.schema`)에서 엔진 표 설계서 등급 `개인` 이상 열을 읽기 계정이 못 읽어야 한다(S-SEC-9 엔진 몫)."""
    classified: dict[str, dict[str, str]] = {}
    for doc in data_classes.design_docs(root):
        if doc.name.startswith("engine") or doc.relative_to(root).parts[:2] == ("crates", "engine"):
            check = data_classes.DocCheck(doc.relative_to(root).as_posix(), doc.read_text(encoding="utf-8"))
            check.run()
            for table, columns in check.classified.items():
                classified.setdefault(table, {}).update(columns)
    reader = quote_literal(f"{target.schema}_ro")
    for table, column in db.query(
        f"SELECT c.relname, a.attname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped "
        f"WHERE n.nspname = {quote_literal(schema)} AND c.relkind IN ('r', 'p') AND has_column_privilege({reader}, c.oid, a.attnum, 'SELECT') ORDER BY 1, 2"
    ).rows:
        grade = classified.get(table or "", {}).get(column or "")
        if grade is not None and data_classes.RANK.get(grade, 0) >= data_classes.RANK["개인"]:
            problems.append(f"{target.rel}: S-SEC-9 엔진 공유 스키마 `{schema}.{table}.{column}`(등급 `{grade}`)을 읽기 계정이 읽을 수 있음")


def run_target(config: dict, target: Target, root: Path, waivers: list[pending.Pending]) -> list[str]:
    """이관 폴더 하나를 새 DB에 적용하고 목록으로 본다. 이관(엔진 이관 단계 또는 흉내)이 실패하면 뒤 검사는 건너뛴다 — 반쯤 된 스키마에
    질의하면 `42P01` 같은 예외가 S-MIG-8(진짜 원인)을 가린다(2026-11-05, PostgreSQL 16에서 `transaction_timeout` 거부). 그래도 남는
    검사 질의 오류(PgError)는 문제 한 줄로 적고 traceback 없이 끝낸다."""
    problems: list[str] = []
    run = f"{os.getpid()}_{secrets.token_hex(3)}"
    database = f"mookko_dbcheck_{target.schema}_{run}"[:63]
    key_database: str | None = None
    key_target: Target | None = None
    password = secrets.token_hex(16)
    with connect(config, config["user"], config["password"], config["database"]) as admin:
        try:
            app = engine_app(root, target)
            if app is not None and not isinstance(app.example.get("migrate"), dict):
                # 실행 파일의 이관 설정 예시가 엔진 이관 설정 모양({"migrate": {databases, …}})이 아니면 실제 이관을 시험할 수 없음.
                # 멈추지 말고(KeyError) 그 사실을 문제 줄로 낸다(11-10 pensive 후보: mookko-logs 예시가 telemetry·clickhouse·postgres 모양).
                problems.append(f"{target.rel}: 이관 설정 예시 {migrate_example(root, target.service).relative_to(root).as_posix()}에 엔진 이관 칸 "
                                f"`migrate`가 없습니다 — 엔진 migrate 설정 모양으로 맞추세요(실제 이관 시험을 하지 못함, S-MIG-11)")
                return problems
            shared = (app.example["migrate"].get("sharedStores") or {}).get("schema") if app else None
            # 키 DB(§9.8)에는 읽기·대사 계정이 없음: 서비스 코드의 읽기 설정을 쓰지 않고 닫힌 기본 그대로 본다.
            key_db = is_key_dir(Path(target.rel))
            access = data_classes.ReaderAccess() if key_db else data_classes.reader_access(target.directory.parent, root)
            bootstrap(admin, database, target.schema, password)
            with connect(config, config["user"], config["password"], database) as db_admin:
                bootstrap_schema(db_admin, target.schema, (shared,) if shared else ())
            key_target = engine_key_target(root, target, app, problems) if app is not None else None
            if key_target is not None:
                key_database = f"mookko_dbcheck_{key_target.schema}_{run}"[:63]
                bootstrap(admin, key_database, key_target.schema, password)
                with connect(config, config["user"], config["password"], key_database) as db_admin:
                    bootstrap_schema(db_admin, key_target.schema)
            applied = 0
            if app is not None:
                # 실제 엔진 이관 단계: 이관 적용·grant·grant_recon·파티션 만들기(와 키 DB 이관·grant_key_store)를 엔진이 한 뒤 목록으로 본다.
                ok = engine_migrate(config, target, app, database, key_database, password, access, problems)
                if ok:
                    with connect(config, config["user"], config["password"], database) as db_admin:
                        applied = int(db_admin.query(f"SELECT count(*) FROM {quote_ident(target.schema)}.schema_migrations").rows[0][0] or 0)
            else:
                before = len(problems)
                with connect(config, f"{target.schema}_migrate", password, database) as migrate:
                    applied = apply_files(migrate, target, problems)
                ok = len(problems) == before
            how = "엔진 이관 단계" if app is not None else "엔진 흉내(표본)"
            if not ok:
                # 이관이 안 된(또는 반쯤 된) 스키마를 검사하면 없는 표 질의(42P01) 같은 예외가 S-MIG-8을 가리므로 여기서 멈춘다.
                problems.append(f"{target.rel}: 이관이 실패해 뒤 검사(목록·읽기·대사·파티션)는 건너뜀")
                print(f"  {target.rel}: 스키마 {target.schema}, 이관 실패({how}) — 뒤 검사 건너뜀")
            else:
                with connect(config, config["user"], config["password"], database) as db_admin:
                    if app is None:
                        grant_like_engine(db_admin, target, access)
                        grant_recon_like_engine(db_admin, target, access)
                    catalog_checks(db_admin, target, problems)
                    if key_db:
                        key_db_checks(db_admin, target, problems)
                    classified = data_classes.service_classification(root, target.service)
                    reader_checks(db_admin, target, classified, access, waivers, problems)
                    recon_checks(db_admin, target, classified, access, problems)
                    if app is not None:
                        partition_checks(db_admin, target, problems)
                        if shared:
                            shared_reader_checks(db_admin, target, shared, root, problems)
                print(f"  {target.rel}: 스키마 {target.schema}, 이관 {applied}개 적용({how})")
                if key_target is not None and key_database is not None:
                    key_checks_after_engine(config, key_target, key_database, problems)
        except PgError as error:
            # 검사 질의가 실패하면 traceback 대신 문제 한 줄(대상·SQLSTATE·서버 글)로 적는다. 종료 코드는 main이 1로 만든다.
            problems.append(f"{target.rel}: 검사 질의 실패({error.sqlstate}): {error.message}")
        finally:
            admin.query(f"DROP DATABASE IF EXISTS {quote_ident(database)} WITH (FORCE)")
            if key_database is not None:
                admin.query(f"DROP DATABASE IF EXISTS {quote_ident(key_database)} WITH (FORCE)")
            for schema in [target.schema] + ([key_target.schema] if key_target is not None else []):
                for suffix in ROLE_SUFFIXES:
                    admin.query(f"DROP ROLE IF EXISTS {quote_ident(f'{schema}_{suffix}')}")
    return problems


def key_dir_of(target: Target) -> Path:
    return target.directory.parent / "keys" / "migrations"


def engine_key_target(root: Path, target: Target, app: EngineApp, problems: list[str]) -> Target | None:
    """실행 파일이 있는 서비스의 키 DB 폴더(`keys/migrations`)를 엔진 이관 단계로 돌릴 대상. 폴더가 있는데 이관 설정 예시에
    `keyDatabases.<서비스>`가 없으면 엔진이 키 DB 이관을 하지 않으므로(모듈이 `key_migrations`를 비워도 조용히 지나감) 실패로 적는다.
    거꾸로 예시에만 있고 모듈에 키 이관이 없으면 엔진이 거부한다(S-MIG-8로 보임)."""
    directory = key_dir_of(target)
    entries = app.example["migrate"].get("keyDatabases") or {}
    if not directory.is_dir():
        return None
    rel = directory.relative_to(root)
    if target.service not in entries:
        problems.append(f"{rel.as_posix()}: S-SEC-10 키 DB 이관이 있는데 이관 설정 예시에 `keyDatabases.{target.service}`가 없음 — 엔진 이관 단계가 키 DB를 돌리지 않음")
        return None
    return Target(directory, rel.as_posix(), default_schema(rel) or f"{target.service}_keys", target.service)


def key_checks_after_engine(config: dict, key_target: Target, key_database: str, problems: list[str]) -> None:
    """엔진이 키 DB 이관과 `grant_key_store`를 한 뒤: 적용 수가 폴더의 파일 수와 같은지(모듈이 폴더를 다 넣었는지), 그리고 흉내 길과
    같은 목록 검사(catalog·key_db)."""
    files = sorted(p for p in key_target.directory.glob("*.sql"))
    with connect(config, config["user"], config["password"], key_database) as db_admin:
        applied = int(db_admin.query(f"SELECT count(*) FROM {quote_ident(key_target.schema)}.schema_migrations").rows[0][0] or 0)
        if applied != len(files):
            problems.append(f"{key_target.rel}: S-SEC-10 엔진이 키 DB 이관을 {applied}개 적용했는데 폴더에는 {len(files)}개 — 서비스 모듈 `key_migrations`가 폴더를 다 넣지 않음")
        catalog_checks(db_admin, key_target, problems)
        key_db_checks(db_admin, key_target, problems)
    print(f"  {key_target.rel}: 스키마 {key_target.schema}, 이관 {applied}개 적용(엔진 이관 단계)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="검사할 저장소 뿌리(시험용)")
    parser.add_argument("--pending", type=Path, default=pending.LIST, help="기한부 유예 목록(시험용)")
    args = parser.parse_args(argv)
    config = load_config()
    if config is None:
        if os.environ.get("MOOKKO_REQUIRE_TEST_POSTGRES") == "1":
            print("migration apply failed: MOOKKO_TEST_POSTGRES가 없음(dev/with-test-postgres.sh 안에서 실행)")
            return 1
        print("migration apply 건너뜀(통과 아님): MOOKKO_TEST_POSTGRES가 없음")
        return 0
    root = args.root.resolve()
    found = targets(root)
    problems: list[str] = []
    waivers = pending.load(problems, args.pending)
    for target in found:
        if is_key_dir(Path(target.rel)) and migrate_example(root, target.service).is_file():
            continue  # 서비스 DB와 같은 `migrate` 실행에서 엔진이 돌림(run_target → engine_key_target)
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", target.schema):
            problems.append(f"{target.rel}: S-TYPE-6 스키마 이름 `{target.schema}`")
            continue
        problems += run_target(config, target, root, waivers)
    if problems:
        # 문제 줄을 먼저 내고 마지막 줄은 늘 요약(`migration apply failed (N problems)`) — 로그 끝만 봐도 결과를 알 수 있게.
        for p in problems:
            print(f"  - {p}")
        print(f"migration apply failed ({len(problems)} problems)")
        return 1
    print(f"migration apply passed ({len(found)} dirs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

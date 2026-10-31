"""이관 파일 검사 (docs/policy/conventions/sql.md, docs/architecture/database.md §7).

라이브 패치 동안 신구 판이 같은 DB를 쓰므로, 긴 잠금·다시 쓰기·옛 판을 깨는 변경이 이관에 들어오지 못하게 막는다.
- `crates/**/migrations/*.sql`을 읽는다(경로에 `clickhouse`가 들면 ClickHouse 규칙, 아니면 PostgreSQL 규칙).
- Rust 소스(`crates/**/*.rs`)의 문자열 안 `SELECT *`·`RETURNING *`도 찾는다(S-Q-2).
- 판정은 규칙 번호(S-*)와 함께 `파일:줄`로 알린다. 하나라도 있으면 종료 코드 1.
완전한 SQL 파서가 아니라 정해진 모양을 찾는 검사다. 잡지 못하는 것은 실제 적용 시험(migration_apply.py)과 QA가 본다.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import migration_lock  # noqa: E402
import pending  # noqa: E402
import sqltext  # noqa: E402
from sqltext import IDENT, QNAME, parse_qname, paren_body, split_top_level  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist"}
FILE_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
PHASES = {"expand", "migrate", "contract"}
KNOWN_DIRECTIVES = {"phase", "transaction", "schema", "validate-deploy"}
# 덧붙이기만 하는 표(이름에 ledger·journal·audit). 사슬·구간 머리(`…_head`, `…_heads`)는 지금 상태를 고쳐 쓰는 표라 뺀다.
APPEND_ONLY = re.compile(r"^(?!.*_heads?$).*(ledger|journal|audit)")
AMOUNT_NAME = re.compile(r"(^|_)(amount|balance|price|fee)s?($|_)|_minor$")
VOLATILE = re.compile(
    r"\b(clock_timestamp|random|gen_random_uuid|uuidv4|uuidv7|uuid_generate_v\d\w*|timeofday|nextval|"
    r"txid_current|pg_current_xact_id)\s*\(",
    re.I,
)
ROLE_SUFFIXES = ("owner", "migrate", "app", "ro", "recon", "maint", "audit_reader")  # sql.md S-BND-2·5 계정 접미어
SCHEMA_PLACEHOLDER = "__schema__"  # 이관기가 자기 스키마 이름으로 바꾸는 자리 표시(`__SCHEMA__.테이블`)
SNAKE = re.compile(r"^[a-z_][a-z0-9_]*$")
IS = re.I | re.S

SELECT_STAR = re.compile(r"(?:\bSELECT\s+(?:ALL\s+|DISTINCT\s+)?|,\s*)(?:[A-Za-z_][A-Za-z0-9_]*\s*\.\s*)?\*(?!\s*\))", re.I)
RETURNING_STAR = re.compile(r"\bRETURNING\s+\*", re.I)


@dataclass(frozen=True)
class Finding:
    """검사 결과 하나."""

    path: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} {self.message}"


def lock_timeout_ms(raw: str) -> int | None:
    """`SET LOCAL lock_timeout = '3s'`의 값을 밀리초로. 읽을 수 없으면 None."""
    match = re.search(r"lock_timeout\s*(?:=|\bTO\b)\s*'?\s*(\d+)\s*(ms|s|min)?\s*'?", raw, re.I)
    if not match:
        return None
    value = int(match.group(1))
    unit = (match.group(2) or "ms").lower()
    return value * {"ms": 1, "s": 1000, "min": 60000}[unit]


def column_type(rest: str) -> str:
    """열 정의에서 형식 부분(제약 낱말 앞까지, 괄호 밖 기준)."""
    stop = re.compile(
        r"(NOT\s+NULL|NULL|DEFAULT|CONSTRAINT|PRIMARY\s+KEY|UNIQUE|CHECK|REFERENCES|GENERATED|COLLATE|"
        r"CODEC|TTL|MATERIALIZED|ALIAS|COMMENT|EPHEMERAL)\b",
        re.I,
    )
    depth = 0
    i = 0
    while i < len(rest):
        ch = rest[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and (i == 0 or rest[i - 1] == " ") and stop.match(rest, i):
            return rest[:i].strip()
        i += 1
    return rest.strip()


def bad_type(type_text: str) -> tuple[str, str] | None:
    """PostgreSQL 형식 규칙(S-TYPE-*, S-MONEY-1)."""
    t = " ".join(type_text.lower().split())
    t = re.sub(r"(\s*\[\s*\d*\s*\])+$", "", t)
    t = re.sub(r"^pg_catalog\.", "", t)
    if re.fullmatch(r"timestamp(\s*\(\s*\d+\s*\))?(\s+without\s+time\s+zone)?", t):
        return "S-TYPE-1", f"`{type_text}`: timestamptz만 씀"
    if re.fullmatch(r"timetz|time(\s*\(\s*\d+\s*\))?\s+with\s+time\s+zone", t):
        return "S-TYPE-1", f"`{type_text}`: 시간대 있는 time 금지"
    if re.fullmatch(r"real|float[48]?|float\s*\(\s*\d+\s*\)|double\s+precision|numeric.*|decimal.*|money", t):
        return "S-MONEY-1", f"`{type_text}`: 실수·numeric·money 금지(돈은 bigint 최소 단위)"
    if re.fullmatch(r"(varchar|character\s+varying)(\s*\(.*\))?", t):
        return "S-TYPE-2", f"`{type_text}`: text + CHECK(char_length)로"
    match = re.fullmatch(r"(char|character|bpchar)(\s*\(\s*(\d+)\s*\))?", t)
    if match and match.group(3) != "3":
        return "S-TYPE-2", f"`{type_text}`: char는 통화 char(3)만"
    if t == "json":
        return "S-TYPE-3", "`json` 대신 `jsonb`"
    if t in {"serial", "bigserial", "smallserial", "serial2", "serial4", "serial8"}:
        return "S-TYPE-5", f"`{type_text}`: identity 또는 UUIDv7"
    return None


@dataclass
class TableInfo:
    """이 파일에서 만든 테이블."""

    line: int
    columns: dict[str, str] = field(default_factory=dict)
    is_partition: bool = False
    partitioned: bool = False


class FileLint:
    """이관 파일 하나의 판정."""

    def __init__(
        self, rel: str, script: sqltext.Script, dialect: str, schema: str | None, engine_tx_off: bool = False, engine_fixed: bool = False
    ) -> None:
        self.rel = rel
        self.engine_fixed = engine_fixed  # 엔진 생성 SQL 고정 파일(engine-generated.json, SHA 일치): phase 머리·따옴표 이름만 건너뜀
        self.script = script
        self.engine_tx_off = engine_tx_off  # 엔진 이관기가 이 파일을 트랜잭션 밖에서 돌리는지(머리 규칙)
        self.dialect = dialect
        self.schema = schema
        self.findings: list[Finding] = []
        self.created: dict[str, TableInfo] = {}
        self.triggers: dict[str, set[str]] = {}
        self.added: dict[str, list[str]] = {}  # ALTER TABLE … ADD COLUMN으로 더한 열(설계서 대조용)
        self.validated = False
        self.lock_timeout_set = False
        phase = script.directives.get("phase")
        self.phase = phase[0] if phase else None
        tx = script.directives.get("transaction")
        self.tx_off = bool(tx and tx[0] == "off")

    def add(self, line: int, rule: str, message: str) -> None:
        self.findings.append(Finding(self.rel, line, rule, message))

    # ---- 머리 ----
    def check_header(self) -> None:
        d = self.script.directives
        for name, (_, line) in d.items():
            if name not in KNOWN_DIRECTIVES:
                self.add(line, "S-MIG-4", f"모르는 머리 지시 `mookko:{name}`(phase·transaction·schema·validate-deploy만)")
        for name, line in self.script.duplicate_directives:
            self.add(line, "S-MIG-4", f"머리 지시 `mookko:{name}`가 두 번")
        for line in self.script.late_directives:
            self.add(line, "S-MIG-4", "`-- mookko:` 지시는 첫 문장 앞 머리에만")
        if self.phase is None:
            if not self.engine_fixed:
                self.add(1, "S-MIG-4", "머리에 `-- mookko:phase expand|migrate|contract`가 없음")
        elif self.phase not in PHASES:
            self.add(d["phase"][1], "S-MIG-4", f"phase `{self.phase}`: expand·migrate·contract 중 하나")
        if "transaction" in d and d["transaction"][0] != "off":
            self.add(d["transaction"][1], "S-MIG-6", "`-- mookko:transaction`은 `off`만")
        if self.dialect == "postgres" and not self.schema:
            self.add(1, "S-BND-1", "스키마를 정할 수 없음(`crates/services/<서비스>/migrations/` 밖이면 `-- mookko:schema <이름>`)")
        if not self.script.statements:
            self.add(1, "S-MIG-1", "문장이 없는 이관 파일")

    # ---- 공통 ----
    def check_common(self, st: sqltext.Statement) -> None:
        t = st.text
        if SELECT_STAR.search(t) or RETURNING_STAR.search(t):
            self.add(st.line, "S-Q-2", "`SELECT *`·`t.*`·`RETURNING *` 금지(열을 적음)")

    # ---- PostgreSQL ----
    def existing(self, name: str) -> bool:
        return parse_qname(name)[1] not in self.created

    def check_name(self, line: int, name: str, what: str) -> None:
        if '"' in name:
            return  # check_forbidden이 알림
        _, bare = parse_qname(name)
        if not SNAKE.match(bare):
            self.add(line, "S-TYPE-6", f"{what} `{bare}`: snake_case ASCII")
        if len(bare.encode("utf-8")) > 63:
            self.add(line, "S-TYPE-6", f"{what} `{bare}`: 63바이트를 넘으면 PostgreSQL이 잘라 이름이 겹침")

    def check_schema_refs(self, st: sqltext.Statement) -> None:
        allowed = {self.schema, SCHEMA_PLACEHOLDER, "pg_catalog", "information_schema"}
        t = st.text
        refs = re.findall(
            rf"\b(?:TABLE|INTO|FROM|JOIN|UPDATE|REFERENCES|VIEW|FUNCTION|PROCEDURE|SEQUENCE|TYPE|"
            rf"EXECUTE\s+FUNCTION|EXECUTE\s+PROCEDURE|ONLY|EXISTS|OF|TRUNCATE|INDEX|TRIGGER)\s+({IDENT}\s*\.\s*{IDENT})",
            t,
            re.I,
        )
        if re.match(r"^(CREATE\s+(UNIQUE\s+)?INDEX|CREATE\s+(OR\s+REPLACE\s+)?(CONSTRAINT\s+)?TRIGGER|GRANT|REVOKE|COMMENT|CREATE\s+POLICY)\b", t, re.I):
            refs += re.findall(rf"\bON\s+(?:TABLE\s+|FUNCTION\s+|SEQUENCE\s+)?(?:ONLY\s+)?({IDENT}\s*\.\s*{IDENT})", t, re.I)
        for ref in refs:
            schema, _ = parse_qname(ref)
            if schema is not None and schema not in allowed:
                self.add(st.line, "S-BND-1", f"다른 스키마 `{schema}` 참조(자기 스키마 `{self.schema}`·pg_catalog만)")
        for name in re.findall(rf"\bSCHEMA\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?({IDENT})", t, re.I):
            _, bare = parse_qname(name)
            if bare not in allowed:
                self.add(st.line, "S-BND-1", f"다른 스키마 `{bare}`(자기 스키마 `{self.schema}`만)")

    def check_forbidden(self, st: sqltext.Statement) -> None:
        t = st.text
        if re.search(r"\bdblink\w*\b|\bpostgres_fdw\b|^CREATE\s+(SERVER|FOREIGN\s+(TABLE|DATA\s+WRAPPER)|USER\s+MAPPING)\b|^IMPORT\s+FOREIGN\s+SCHEMA\b", t, re.I):
            self.add(st.line, "S-BND-3", "다른 DB에 닿는 기능(dblink·fdw) 금지 — 연결은 gRPC")
        if re.match(r"^COPY\b", t, re.I) and re.search(r"\bPROGRAM\b|\b(FROM|TO)\s+''", t, re.I):
            self.add(st.line, "S-BND-3", "서버 파일·프로그램 COPY 금지")
        if re.match(r"^(CREATE|ALTER|DROP)\s+(ROLE|USER|GROUP)\b|^(CREATE|ALTER|DROP)\s+DATABASE\b|^CREATE\s+EXTENSION\b|^ALTER\s+SYSTEM\b", t, re.I):
            self.add(st.line, "S-BND-4", "계정·DB·확장·서버 설정은 서비스 이관이 아니라 DB 준비 스크립트에서")
        if re.match(r"^CREATE\s+TYPE\b.*\bAS\s+ENUM\b", t, re.I):
            self.add(st.line, "S-TYPE-4", "enum 금지 → text + CHECK (c IN (…))")
        if re.search(r"\b(pgp_sym_encrypt|pgp_pub_encrypt|pgp_sym_decrypt|pgp_pub_decrypt|encrypt_iv|decrypt_iv|encrypt|decrypt|crypt|gen_salt)\s*\(", t, re.I):
            self.add(st.line, "S-SEC-7", "DB 안 암호화(pgcrypto) 금지 — 엔진 FieldCipher")
        if '"' in t and not self.engine_fixed:
            self.add(st.line, "S-TYPE-6", "큰따옴표 이름 금지")
        if re.match(r"^SET\b", t, re.I) and not re.match(r"^SET\s+LOCAL\b", t, re.I):
            self.add(st.line, "S-MIG-5", "`SET`은 `SET LOCAL`로만(세션 설정이 풀 접속에 남음)")
        if re.match(r"^(BEGIN|COMMIT|ROLLBACK|START\s+TRANSACTION|END|SAVEPOINT)\b", t, re.I):
            self.add(st.line, "S-MIG-6", "트랜잭션은 이관기가 연다(파일에 BEGIN·COMMIT 금지)")

    def check_grant(self, st: sqltext.Statement) -> None:
        t = st.text
        if not re.match(r"^GRANT\b", t, re.I):
            return
        if re.search(r"\bTO\s+(?:.*,\s*)?PUBLIC\b", t, re.I) or re.search(r"^GRANT\s+ALL\b", t, re.I) or re.search(r"\bWITH\s+(GRANT|ADMIN)\s+OPTION\b", t, re.I):
            self.add(st.line, "S-BND-5", "`TO PUBLIC`·`GRANT ALL`·`WITH GRANT OPTION` 금지")
        to = re.search(r"\bTO\s+(.+?)(?:\s+WITH\b|\s+GRANTED\s+BY\b|$)", t, re.I)
        grantees = [parse_qname(g)[1] for g in to.group(1).split(",")] if to else []
        for grantee in grantees:
            # 자기 서비스 계정만: `<스키마>_` + S-BND-2 접미어 목록(넓히기는 규약 변경 — 사용자 결정).
            allowed = {f"{self.schema}_{suffix}" for suffix in ROLE_SUFFIXES}
            if grantee != "public" and grantee not in allowed:
                self.add(st.line, "S-BND-5", f"`{grantee}`에게 GRANT: 자기 서비스 계정({', '.join(sorted(allowed))})만")
        if re.match(r"^GRANT\s+(?:[A-Z ,]*\b)?(CREATE|TEMPORARY|TEMP)\b[^;]*\bON\s+(SCHEMA|DATABASE)\b", t, re.I):
            self.add(st.line, "S-BND-2", "스키마·DB에 CREATE 권한을 주지 않음(DDL은 주인 역할만)")
        privs = re.match(r"^GRANT\s+(.+?)\s+ON\b", t, re.I)
        on = re.search(r"\bON\s+(?:TABLE\s+)?(.+?)\s+TO\b", t, re.I)
        if privs and on and re.search(r"\b(UPDATE|DELETE|TRUNCATE)\b", privs.group(1), re.I):
            for obj in on.group(1).split(","):
                if APPEND_ONLY.search(parse_qname(obj)[1]):
                    self.add(st.line, "S-MONEY-2", f"덧붙이기만 하는 `{parse_qname(obj)[1]}`에 UPDATE·DELETE·TRUNCATE 권한 금지")

    def check_create_table(self, st: sqltext.Statement) -> bool:
        m = re.match(
            rf"^CREATE\s+(?P<mods>(?:(?:GLOBAL|LOCAL)\s+)?(?:TEMP|TEMPORARY|UNLOGGED)\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>{QNAME})\s*(?P<rest>.*)$",
            st.text,
            IS,
        )
        if not m:
            return False
        name = m.group("name")
        _, bare = parse_qname(name)
        self.check_name(st.line, name, "테이블")
        info = TableInfo(line=st.line)
        self.created[bare] = info
        if self.phase == "contract":
            self.add(st.line, "S-MIG-4", "contract 파일에 CREATE TABLE(넓히기)을 섞지 않음")
        if m.group("mods"):
            self.add(st.line, "S-MIG-2h", "UNLOGGED·TEMP 테이블 금지(복제·장애 전환에서 사라짐)")
        rest = m.group("rest")
        if re.match(r"^PARTITION\s+OF\b", rest, re.I):
            info.is_partition = True
            if self.dialect == "postgres":
                self.add(st.line, "S-PART-3", "달 파티션은 이관이 만들지 않음 — 부모만 만들고 엔진 `partitioned`가 `<표>_YYYYMM`을 만듦(E-DB-5)")
            if re.search(rf"^PARTITION\s+OF\s+{QNAME}\s+DEFAULT\b", rest, re.I):
                self.add(st.line, "S-PART-2", "기본(DEFAULT) 파티션 금지 — 앞 파티션을 미리 만듦")
            return True
        if re.match(r"^AS\b", rest, re.I) or re.search(r"\)\s*AS\s+(SELECT|TABLE|VALUES|WITH)\b", rest, re.I):
            self.add(st.line, "S-MIG-3", "CREATE TABLE AS 금지(기본 키 없음, 데이터 복사)")
            return True
        if not rest.startswith("("):
            self.add(st.line, "S-MIG-3", "열 목록을 읽을 수 없음")
            return True
        body, after = paren_body(rest, 0)
        info.partitioned = bool(re.search(r"\bPARTITION\s+BY\b", rest[after:], re.I))
        has_pk = False
        keys: list[tuple[str, list[str]]] = []
        for element in split_top_level(body):
            if re.match(r"^(CONSTRAINT|PRIMARY|UNIQUE|CHECK|FOREIGN|EXCLUDE|LIKE)\b", element, re.I):
                cname = re.match(rf"^CONSTRAINT\s+({IDENT})", element, re.I)
                if cname:
                    self.check_name(st.line, cname.group(1), "제약")
                key = re.search(r"\b(PRIMARY\s+KEY|UNIQUE)\s*(?:NULLS\s+(?:NOT\s+)?DISTINCT\s*)?\(([^)]*)\)", element, re.I)
                if key:
                    keys.append((" ".join(key.group(1).upper().split()), [parse_qname(c)[1] for c in key.group(2).split(",")]))
                if re.search(r"\bPRIMARY\s+KEY\b", element, re.I):
                    has_pk = True
                continue
            col = re.match(rf"^({IDENT})\s+(.*)$", element, IS)
            if not col:
                continue
            cname = col.group(1)
            ctype = column_type(col.group(2))
            self.check_name(st.line, cname, "열")
            _, cbare = parse_qname(cname)
            info.columns[cbare] = ctype
            if re.search(r"\bPRIMARY\s+KEY\b", col.group(2), re.I):
                has_pk = True
                keys.append(("PRIMARY KEY", [cbare]))
            elif re.search(r"\bUNIQUE\b", col.group(2), re.I):
                keys.append(("UNIQUE", [cbare]))
            self.check_column_type(st.line, bare, cbare, ctype)
        part = re.search(r"\bPARTITION\s+BY\s+(?:RANGE|LIST|HASH)\s*\(([^)]*)\)", rest[after:], re.I)
        if part:
            part_cols = {parse_qname(c)[1] for c in part.group(1).split(",") if re.fullmatch(r"\s*[A-Za-z_][A-Za-z0-9_]*\s*", c)}
            for kind, cols in keys:
                missing = part_cols - set(cols)
                if missing:
                    self.add(st.line, "S-PART-1", f"`{bare}` {kind}({', '.join(cols)})에 파티션 키 {', '.join(sorted(missing))}가 없음(PostgreSQL이 거부)")
        if not has_pk:
            self.add(st.line, "S-MIG-3", f"`{bare}`에 기본 키가 없음")
        if any(AMOUNT_NAME.search(c) and not c.endswith("currency") for c in info.columns) and not any(c.endswith("currency") for c in info.columns):
            self.add(st.line, "S-MONEY-1", f"`{bare}`: 금액 열이 있으면 같은 테이블에 `…currency char(3)` 열")
        return True

    def check_column_type(self, line: int, table: str, column: str, ctype: str) -> None:
        problem = bad_type(ctype)
        if problem:
            self.add(line, problem[0], f"`{table}.{column}` {problem[1]}")
        if AMOUNT_NAME.search(column) and not column.endswith("currency") and not re.fullmatch(r"(bigint|int8)(\s*\[\s*\])?", ctype.strip().lower()):
            self.add(line, "S-MONEY-1", f"`{table}.{column}`: 금액 열은 bigint(최소 단위)")

    def check_create_index(self, st: sqltext.Statement) -> bool:
        m = re.match(
            rf"^CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?P<conc>CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(?:(?P<iname>{IDENT})\s+)?ON\s+(?P<only>ONLY\s+)?(?P<table>{QNAME})",
            st.text,
            re.I,
        )
        if not m:
            return False
        if m.group("iname"):
            self.check_name(st.line, m.group("iname"), "색인")
        if self.existing(m.group("table")) and not m.group("conc") and not m.group("only"):
            self.add(st.line, "S-MIG-2a", f"기존 테이블 `{parse_qname(m.group('table'))[1]}`의 색인은 CONCURRENTLY로(별도 파일, transaction off)")
            self.touch_existing(st)
        return True

    def touch_existing(self, st: sqltext.Statement) -> None:
        if not self.tx_off and not self.lock_timeout_set:
            self.add(st.line, "S-MIG-5", "기존 테이블을 바꾸기 전에 `SET LOCAL lock_timeout = '3s';`")
            self.lock_timeout_set = True  # 같은 파일에 한 번만 알림

    def check_alter_table(self, st: sqltext.Statement) -> bool:
        m = re.match(rf"^ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?(?P<name>{QNAME})\s*(?P<rest>.*)$", st.text, IS)
        if not m:
            return False
        table = parse_qname(m.group("name"))[1]
        existing = table not in self.created
        rest = m.group("rest")
        if existing:
            self.touch_existing(st)
        for action in split_top_level(rest):
            self.check_alter_action(st, table, existing, action)
        return True

    def check_alter_action(self, st: sqltext.Statement, table: str, existing: bool, a: str) -> None:
        line = st.line
        if re.match(r"^(RENAME|SET\s+SCHEMA)\b", a, re.I):
            if existing:
                self.add(line, "S-MIG-4", f"`{table}` 이름 바꾸기 금지 — 새 열·테이블로 넓히기→옮기기→좁히기")
            return
        if re.match(r"^(DISABLE\s+TRIGGER|ENABLE\s+(REPLICA|ALWAYS)\s+TRIGGER)\b", a, re.I) and APPEND_ONLY.search(table):
            self.add(line, "S-MONEY-2", f"덧붙이기만 하는 `{table}`의 막기 트리거를 끄거나 REPLICA·ALWAYS로 바꿀 수 없음(기본 ENABLE만)")
            return
        add_col = re.match(
            rf"^ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(?!(?:CONSTRAINT|PRIMARY|UNIQUE|CHECK|FOREIGN|EXCLUDE)\b)({IDENT})\s+(.*)$",
            a,
            IS,
        )
        if add_col:
            cname = parse_qname(add_col.group(1))[1]
            body = add_col.group(2)
            ctype = column_type(body)
            self.check_name(line, add_col.group(1), "열")
            self.check_column_type(line, table, cname, ctype)
            self.added.setdefault(table, []).append(cname)
            if self.phase == "contract":
                self.add(line, "S-MIG-4", "contract 파일에 ADD COLUMN(넓히기)을 섞지 않음")
            if existing:
                default = re.search(r"\bDEFAULT\s+(.*?)(?:\s+(?:NOT\s+NULL|NULL|CONSTRAINT|CHECK|REFERENCES|UNIQUE|PRIMARY)\b|$)", body, IS)
                if (default and VOLATILE.search(default.group(1))) or re.search(r"\bGENERATED\b.*\bSTORED\b|\bGENERATED\s+(ALWAYS|BY\s+DEFAULT)\s+AS\s+IDENTITY\b", body, IS) or re.fullmatch(r"(small|big)?serial[248]?", ctype.lower()):
                    self.add(line, "S-MIG-2b", f"`{table}.{cname}`: 휘발 기본값·STORED·identity·serial 열 추가는 테이블을 다시 씀")
                elif re.search(r"\bNOT\s+NULL\b", body, re.I) and not default:
                    self.add(line, "S-MIG-2c", f"`{table}.{cname}`: NOT NULL 열은 상수 기본값과 함께만(아니면 NULL로 넓히고 나중에 굳힘)")
                if re.search(r"\b(UNIQUE|PRIMARY\s+KEY)\b", body, re.I):
                    self.add(line, "S-MIG-2g", f"`{table}.{cname}`: 열 추가와 UNIQUE·PK를 한 문장에 두면 잠근 채 색인을 만듦 — CONCURRENTLY 색인 뒤 USING INDEX")
                if re.search(r"\b(CHECK|REFERENCES)\b", body, re.I):
                    self.add(line, "S-MIG-2f", f"`{table}.{cname}`: 열 추가와 CHECK·REFERENCES를 한 문장에 두면 잠근 채 검증함 — NOT VALID 제약을 따로 더한 뒤 VALIDATE")
            return
        if not existing:
            return
        con = re.match(rf"^ADD\s+(?:CONSTRAINT\s+({IDENT})\s+)?(FOREIGN\s+KEY|CHECK|PRIMARY\s+KEY|UNIQUE|EXCLUDE)\b(.*)$", a, IS)
        if con:
            if con.group(1):
                self.check_name(line, con.group(1), "제약")
            kind = con.group(2).upper()
            if kind.startswith(("FOREIGN", "CHECK")) and not re.search(r"\bNOT\s+VALID\b", a, re.I):
                self.add(line, "S-MIG-2f", f"`{table}`: 외래 키·검사 제약은 NOT VALID로 더하고 다음 파일에서 VALIDATE")
            if kind.startswith(("PRIMARY", "UNIQUE")) and not re.search(r"\bUSING\s+INDEX\b", a, re.I):
                self.add(line, "S-MIG-2g", f"`{table}`: PK·UNIQUE는 CONCURRENTLY 색인을 먼저 만들고 USING INDEX로")
            if kind == "EXCLUDE":
                self.add(line, "S-MIG-2g", f"`{table}`: 기존 테이블에 EXCLUDE 제약 금지")
            return
        if re.match(rf"^ALTER\s+(?:COLUMN\s+)?{IDENT}\s+(?:SET\s+DATA\s+)?TYPE\b", a, re.I):
            self.add(line, "S-MIG-2d", f"`{table}`: 열 형식 바꾸기 금지 — 새 열로 넓히기→옮기기→좁히기")
            return
        if re.match(rf"^ALTER\s+(?:COLUMN\s+)?{IDENT}\s+SET\s+NOT\s+NULL\b", a, re.I):
            if not self.validated:
                self.add(line, "S-MIG-2e", f"`{table}`: SET NOT NULL 전에 같은 파일에서 CHECK (c IS NOT NULL) 제약을 VALIDATE")
            return
        if re.match(r"^VALIDATE\s+CONSTRAINT\b", a, re.I):
            self.validated = True
            return
        drop = re.match(rf"^DROP\s+(?:COLUMN\s+)?(?:IF\s+EXISTS\s+)?(?!(?:CONSTRAINT|DEFAULT|NOT|IDENTITY|EXPRESSION)\b)({IDENT})", a, re.I)
        if drop and self.phase != "contract":
            self.add(line, "S-MIG-4", f"`{table}` 열 지우기는 contract 파일에서만(옛 판이 모두 내려간 뒤)")
            return
        if re.match(r"^(SET\s+(TABLESPACE|LOGGED|UNLOGGED)|CLUSTER\s+ON)\b", a, re.I):
            self.add(line, "S-MIG-2h", f"`{table}`: 테이블을 다시 쓰거나 오래 잠그는 변경 금지")
            return
        if re.match(r"^DETACH\s+PARTITION\b", a, re.I) and not re.search(r"\bCONCURRENTLY\b", a, re.I):
            self.add(line, "S-MIG-2i", f"`{table}`: DETACH PARTITION은 CONCURRENTLY로")

    def check_other_ddl(self, st: sqltext.Statement) -> None:
        t = st.text
        line = st.line
        if re.match(r"^DROP\s+INDEX\b", t, re.I) and not re.match(r"^DROP\s+INDEX\s+CONCURRENTLY\b", t, re.I):
            self.add(line, "S-MIG-2a", "DROP INDEX는 CONCURRENTLY로")
        if re.match(r"^REINDEX\b", t, re.I) and not re.search(r"\bCONCURRENTLY\b", t, re.I):
            self.add(line, "S-MIG-2a", "REINDEX는 CONCURRENTLY로")
        drop = re.match(rf"^DROP\s+(TABLE|VIEW|MATERIALIZED\s+VIEW|SCHEMA|SEQUENCE|TYPE)\s+(?:IF\s+EXISTS\s+)?({QNAME})", t, re.I)
        if drop and self.phase != "contract":
            self.add(line, "S-MIG-4", f"DROP {drop.group(1).upper()}는 contract 파일에서만")
        trig = re.match(rf"^DROP\s+TRIGGER\s+(?:IF\s+EXISTS\s+)?{IDENT}\s+ON\s+({QNAME})", t, re.I)
        if trig and APPEND_ONLY.search(parse_qname(trig.group(1))[1]):
            self.add(line, "S-MONEY-2", "덧붙이기만 하는 테이블의 막기 트리거를 지울 수 없음")
        if re.match(r"^ALTER\s+(VIEW|MATERIALIZED\s+VIEW|SCHEMA|FUNCTION|PROCEDURE|SEQUENCE|TYPE|INDEX)\b.*\b(RENAME|SET\s+SCHEMA)\b", t, re.I):
            self.add(line, "S-MIG-4", "이름 바꾸기 금지(옛 판이 깨짐 — 색인·제약 이름으로 오류를 가르는 코드가 있음)")
        if re.match(r"^DO\b", t, re.I):
            self.add(line, "S-MIG-9", "`DO` 블록 금지(검사가 본문을 볼 수 없음 — 문장을 그대로 씀)")
        if re.match(r"^(SELECT|CALL|EXECUTE|WITH|PERFORM)\b", t, re.I):
            self.add(line, "S-MIG-9", "이관 최상위의 함수 호출·`SELECT`·`CALL`·`WITH` 금지(새 이름 함수로 검사를 피해 데이터를 바꿀 수 있음)")
        if re.search(r"\bsession_replication_role\b", t, re.I):
            self.add(line, "S-MONEY-2", "`session_replication_role`을 바꾸지 않음(막기 트리거가 돌지 않게 됨)")
        if re.match(r"^CREATE\s+OR\s+REPLACE\s+(FUNCTION|PROCEDURE|TRIGGER)\b", t, re.I):
            self.add(line, "S-MIG-9", "`CREATE OR REPLACE` 금지(막기 함수 바꿔치기 방지) — 새 이름으로 만들고 트리거를 옮긴 뒤 contract에서 옛것을 지움")
        if re.match(r"^(TRUNCATE|VACUUM\s+(\(.*\bFULL\b.*\)|FULL)|CLUSTER|LOCK)\b", t, re.I):
            self.add(line, "S-MIG-2h", "TRUNCATE·VACUUM FULL·CLUSTER·LOCK TABLE 금지")
        upd = re.match(rf"^(?:UPDATE\s+(?:ONLY\s+)?|DELETE\s+FROM\s+(?:ONLY\s+)?)({QNAME})", t, re.I)
        if upd and self.existing(upd.group(1)):
            self.add(line, "S-MIG-7", f"이관에서 기존 테이블 `{parse_qname(upd.group(1))[1]}` UPDATE·DELETE 금지 — 배경 이관 작업으로")
        ins = re.match(rf"^INSERT\s+INTO\s+{QNAME}.*?\bSELECT\b.*?\bFROM\s+({QNAME})\s*(\()?", t, IS)
        if ins and not ins.group(2) and self.existing(ins.group(1)):
            self.add(line, "S-MIG-7", "이관에서 기존 테이블을 읽어 채우기(INSERT … SELECT) 금지 — 배경 이관 작업으로, 참조 데이터는 VALUES로")
        if re.match(r"^CREATE\s+(OR\s+REPLACE\s+)?(FUNCTION|PROCEDURE)\b", t, re.I):
            fname = re.match(rf"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+({QNAME})", t, re.I)
            if fname:
                self.check_name(line, fname.group(1), "함수")
            if re.search(r"\bSECURITY\s+DEFINER\b", t, re.I) and not re.search(r"\bSET\s+search_path\b", t, re.I):
                self.add(line, "S-BND-6", "SECURITY DEFINER 함수에 `SET search_path = <스키마>, pg_catalog`")
        trg = re.match(
            rf"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:CONSTRAINT\s+)?TRIGGER\s+({IDENT})\s+(BEFORE|AFTER)\s+(.+?)\s+ON\s+(?:ONLY\s+)?({QNAME})",
            t,
            re.I,
        )
        if trg:
            self.check_name(line, trg.group(1), "트리거")
            events = {e for e in ("UPDATE", "DELETE", "TRUNCATE") if re.search(rf"\b{e}\b", trg.group(3), re.I)}
            self.triggers.setdefault(parse_qname(trg.group(4))[1], set()).update(events)
        if re.match(r"^SET\s+LOCAL\s+lock_timeout\b", t, re.I):
            ms = lock_timeout_ms(st.raw)
            if ms is None or ms <= 0 or ms > 5000:
                self.add(line, "S-MIG-5", "lock_timeout은 0보다 크고 5초 이하")
            self.lock_timeout_set = True

    def check_tx_off(self) -> None:
        stmts = self.script.statements
        if not self.tx_off:
            for st in stmts:
                if re.search(r"\bCONCURRENTLY\b", st.text, re.I):
                    self.add(st.line, "S-MIG-6", "CONCURRENTLY는 트랜잭션 안에서 돌 수 없음 — `-- mookko:transaction off` 파일에 문장 하나로")
            return
        if not self.engine_tx_off:
            self.add(1, "S-MIG-6", "`-- mookko:transaction off`는 머리(앞 빈 줄 뒤 맨 앞에 이어지는 `--` 줄, 사이에 빈 줄 없이) 안에 — 엔진 이관기는 머리만 봄, 아니면 트랜잭션 안에서 돌다 실패")
        if len(stmts) != 1:
            self.add(1, "S-MIG-6", f"transaction off 파일에는 문장 하나만(지금 {len(stmts)}개)")
        for st in stmts:
            # 엔진 `add_concurrent_index`가 받는 모양만: 이름 있는 CREATE [UNIQUE] INDEX CONCURRENTLY IF NOT EXISTS, 표는 스키마를 붙여서.
            if not re.match(
                rf"^CREATE\s+(?:UNIQUE\s+)?INDEX\s+CONCURRENTLY\s+IF\s+NOT\s+EXISTS\s+{IDENT}\s+ON\s+{IDENT}\s*\.\s*{IDENT}", st.text, re.I
            ):
                self.add(
                    st.line,
                    "S-MIG-6",
                    "transaction off 파일은 `CREATE [UNIQUE] INDEX CONCURRENTLY IF NOT EXISTS <이름> ON __SCHEMA__.<표>`만"
                    "(엔진이 DROP·REINDEX·DETACH CONCURRENTLY는 아직 지원하지 않음)",
                )

    def check_append_only(self) -> None:
        for table, info in self.created.items():
            if not APPEND_ONLY.search(table) or info.is_partition:
                continue
            events = self.triggers.get(table, set())
            missing = {"UPDATE", "DELETE", "TRUNCATE"} - events
            if missing:
                self.add(info.line, "S-MONEY-2", f"덧붙이기만 하는 `{table}`에 막기 트리거가 없음: {', '.join(sorted(missing))}")

    def run_postgres(self) -> None:
        for st in self.script.statements:
            self.check_common(st)
            self.check_forbidden(st)
            self.check_schema_refs(st)
            self.check_grant(st)
            if self.check_create_table(st) or self.check_create_index(st) or self.check_alter_table(st):
                continue
            self.check_other_ddl(st)
        self.check_tx_off()
        self.check_append_only()

    # ---- ClickHouse ----
    def run_clickhouse(self) -> None:
        for st in self.script.statements:
            t = st.text
            self.check_common(st)
            self.check_ch_table(st)
            if re.match(rf"^ALTER\s+TABLE\s+{QNAME}(\s+ON\s+CLUSTER\s+\S+)?\s+(UPDATE\b|DELETE\s+WHERE\b)", t, re.I) or re.match(r"^DELETE\s+FROM\b|^UPDATE\b", t, re.I):
                self.add(st.line, "S-CH-2", "데이터 변이(UPDATE·DELETE) 금지 — TTL·파티션 떼기로")
            if re.match(r"^ALTER\s+TABLE\b.*\bMATERIALIZE\s+(COLUMN|INDEX|TTL|PROJECTION|STATISTICS)\b", t, re.I):
                self.add(st.line, "S-CH-2", "MATERIALIZE …는 조각을 다시 씀 — 새 조각부터 적용되게 둠")
            if re.match(r"^OPTIMIZE\s+TABLE\b.*\bFINAL\b", t, re.I):
                self.add(st.line, "S-CH-2", "OPTIMIZE … FINAL 금지")
            if self.phase != "contract" and (
                re.match(r"^(DROP\s+(TABLE|VIEW|DATABASE|DICTIONARY)|RENAME\s+TABLE|EXCHANGE\s+TABLES)\b", t, re.I)
                or re.match(rf"^ALTER\s+TABLE\s+{QNAME}.*\b(DROP|RENAME)\s+COLUMN\b", t, re.I)
            ):
                self.add(st.line, "S-MIG-4", "지우기·이름 바꾸기는 contract 파일에서만")
            self.check_ch_idempotent(st)
            self.check_ch_qualified(st)
            self.check_ch_profile(st)

    def check_ch_table(self, st: sqltext.Statement) -> None:
        t = st.text
        if not re.match(r"^CREATE\s+TABLE\b", t, re.I):
            return
        engine = re.search(r"\bENGINE\s*=\s*(\w*MergeTree)\b", t, re.I)
        if not engine:
            return
        if not re.search(r"\bTTL\b", t, re.I):
            self.add(st.line, "S-CH-1", "MergeTree 테이블에 TTL(보관 기한)이 없음")
        elif not re.search(r"\bmaterialize_ttl_after_modify\s*=\s*0\b", t, re.I):
            self.add(st.line, "S-CH-1", "TTL 표에 `SETTINGS materialize_ttl_after_modify = 0`(기한 바꿀 때 다시 쓰기 방지)")
        if not engine.group(1).lower().startswith("replicated") and not re.search(r"\bnon_replicated_deduplication_window\s*=\s*[1-9]", t, re.I):
            self.add(st.line, "S-CH-5", "복제 아닌 MergeTree에 `non_replicated_deduplication_window`(중복 막기 창)가 없음 — 다시 보낸 묶음이 두 번 들어감")
        if re.search(r"\bORDER\s+BY\s+tuple\s*\(\s*\)", t, re.I):
            self.add(st.line, "S-MIG-3", "`ORDER BY tuple()` 금지 — 조회 앞 조건으로 정렬 키")

    def check_ch_idempotent(self, st: sqltext.Statement) -> None:
        t = st.text
        create = re.match(r"^CREATE\s+(?:OR\s+REPLACE\s+)?(TABLE|MATERIALIZED\s+VIEW|VIEW|DATABASE|DICTIONARY)\b(.*)$", t, re.I | re.S)
        if create and not re.match(r"\s*IF\s+NOT\s+EXISTS\b", create.group(2), re.I):
            self.add(st.line, "S-CH-7", f"CREATE {create.group(1).upper()}는 `IF NOT EXISTS`로(트랜잭션 DDL이 없어 다시 돌릴 수 있게)")
        if re.match(r"^ALTER\s+TABLE\b", t, re.I):
            for action in split_top_level(t):
                if re.search(r"\bADD\s+(COLUMN|INDEX|PROJECTION)\s+(?!IF\s+NOT\s+EXISTS\b)", action, re.I):
                    self.add(st.line, "S-CH-7", "ADD COLUMN·INDEX·PROJECTION은 `IF NOT EXISTS`로")
                if re.search(r"\bDROP\s+(COLUMN|INDEX|PROJECTION)\s+(?!IF\s+EXISTS\b)", action, re.I):
                    self.add(st.line, "S-CH-7", "DROP COLUMN·INDEX·PROJECTION은 `IF EXISTS`로")
        drop = re.match(r"^DROP\s+(TABLE|VIEW|DATABASE|DICTIONARY)\s+(?!IF\s+EXISTS\b)", t, re.I)
        if drop:
            self.add(st.line, "S-CH-7", f"DROP {drop.group(1).upper()}는 `IF EXISTS`로")

    def check_ch_qualified(self, st: sqltext.Statement) -> None:
        t = st.text
        names: list[str] = []
        head = re.match(
            rf"^(?:CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|MATERIALIZED\s+VIEW|VIEW|DICTIONARY)|ALTER\s+TABLE|DROP\s+(?:TABLE|VIEW|DICTIONARY)|"
            rf"INSERT\s+INTO|OPTIMIZE\s+TABLE|TRUNCATE\s+TABLE)\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?({QNAME})",
            t,
            re.I,
        )
        if head:
            names.append(head.group(1))
        names += re.findall(rf"\bTO\s+({QNAME})\s+(?:AS\b|\()", t, re.I)
        for source in re.finditer(rf"\b(?:FROM|JOIN)\s+({QNAME})\s*(\()?", t, re.I):
            if not source.group(2):
                names.append(source.group(1))
        for name in names:
            if "." not in name:
                self.add(st.line, "S-CH-4", f"`{name.strip()}`: 데이터베이스를 붙여 씀(`db.표` 또는 `__DB__.표`)")

    def check_ch_profile(self, st: sqltext.Statement) -> None:
        t = st.raw
        if not re.match(r"^(CREATE|ALTER)\s+(SETTINGS\s+PROFILE|PROFILE|USER)\b", t, re.I):
            return
        if not re.search(r"\breadonly\s*=", t, re.I):
            return
        if re.search(r"\breadonly\s*=\s*'?1\b", t, re.I):
            return
        for limit in ("max_execution_time", "max_memory_usage", "max_rows_to_read", "max_result_rows"):
            bound = re.search(rf"\b{limit}\s*=\s*\S+(?:\s+MIN\s+\S+)?\s+(MAX\b|CONST\b|READONLY\b)", t, re.I)
            if not bound:
                self.add(st.line, "S-CH-6", f"readonly = 2 프로필의 `{limit}`를 `MAX …` 또는 `CONST`로 묶음(질의가 상한을 올리지 못하게)")

    def run(self) -> list[Finding]:
        self.check_header()
        if self.dialect == "clickhouse":
            self.run_clickhouse()
        else:
            self.run_postgres()
        return self.findings


def lint_text(rel: str, sql: str, dialect: str, schema: str | None, engine_fixed: bool = False) -> list[Finding]:
    """이관 SQL 글 하나를 판정한다(시험이 직접 부름)."""
    return FileLint(rel, sqltext.split(sql), dialect, schema, outside_transaction(sql), engine_fixed).run()


ENGINE_GENERATED = Path(__file__).resolve().parent / "engine-generated.json"


def text_sha(text: str) -> str:
    """등록부의 SHA-256: 파일 글 그대로(자리 표시 `__SCHEMA__` 포함), 줄 끝만 LF로."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def engine_fixed_status(rel: str, text: str, registry: dict, today: datetime.date | None = None) -> tuple[bool, str | None]:
    """(예외 적용 여부, 문제). 등록부에 없으면 (False, None). 있는데 SHA가 다르거나 기한이 지났거나 칸이 빠졌으면 예외 없이 문제."""
    for entry in registry.get("files", []):
        if entry.get("path") != rel:
            continue
        missing = [k for k in ("path", "sha256", "reason", "expires", "approvedBy", "source") if not entry.get(k)]
        if missing:
            return False, f"engine-generated.json 항목에 {missing} 칸이 없음"
        if datetime.date.fromisoformat(entry["expires"]) < (today or datetime.date.today()):
            return False, f"엔진 생성 고정 파일 예외가 {entry['expires']}에 끝남"
        if text_sha(text) != entry["sha256"]:
            return False, None  # 내용이 등록부 SHA와 다르면 예외 없이 보통 규칙으로 판정(고친 고정 파일은 머리·따옴표 규칙이 잡음)
        return True, None
    return False, None


def engine_fixed_tests(root: Path, registry: dict) -> list[Finding]:
    """등록된 고정 파일마다 "파일 글 = 엔진 함수 출력(`__SCHEMA__` 바꾼 뒤)"을 엔진 이관기가 확인해야 한다(S-MIG-11):
    그 서비스 코드(주석 뺀 글)에 `SchemaMigrator::add_generated(` 호출과 고정 파일 이름이 함께 있어야 한다(E-DB-14, 이관기가 머리를 뗀
    본문을 엔진 출력과 글자로 비교해 다르면 거부). 옛 `test` 칸(비교 Rust 시험)은 모니터링이 옮긴 뒤(a55c6d9, 통합 b5e9618) 받지 않는다."""
    findings: list[Finding] = []
    for entry in registry.get("files", []):
        where = entry.get("path", "scripts/ci/db/engine-generated.json")
        parts = where.split("/")
        texts: list[str] = []
        if len(parts) >= 3 and parts[:2] == ["crates", "services"]:
            src = root.joinpath(*parts[:3], "src")
            texts = [strip_rust_comments(p.read_text(encoding="utf-8")) for p in walk(src, lambda name: name.endswith(".rs"))]
        stem = Path(where).stem
        if not any("add_generated(" in t and stem in t for t in texts):
            findings.append(Finding(where, 1, "S-MIG-11", f"고정 파일 `{Path(where).name}`을 서비스 코드가 엔진 `add_generated`로 넣지 않음(E-DB-14)"))
    return findings


def code_id_to_file_findings(root: Path, since: str) -> list[tuple[str, str]] | None:
    """`since` 뒤 커밋이 새로 더한(A) 이관 파일의 ID를, 그 바로 앞 커밋의 서비스 코드가 이미 글자로 쓰고 있었으면(코드로 적용하던 이관)
    — 파일 내용이 엔진 출력과 같아야 하므로 — 엔진 생성 고정 파일로 등록돼 있고 그 커밋의 내용이 등록 SHA와 같아야 한다(S-MIG-11).
    git을 못 읽으면 None."""
    commits = migration_lock.history_commits(root, since)
    if commits is None:
        return None
    registry = json.loads(ENGINE_GENERATED.read_text(encoding="utf-8"))
    registered = {e.get("path"): e.get("sha256") for e in registry.get("files", [])}
    problems: list[tuple[str, str]] = []
    for sha, _, changes in commits:
        for status, path in changes:
            parts = path.split("/")
            if status[:1] != "A" or len(parts) < 5 or parts[:2] != ["crates", "services"] or parts[3] != "migrations":
                continue
            ident = parts[-1].removesuffix(".sql")
            src = "/".join(parts[:3] + ["src"])
            used = migration_lock.git(root, "grep", "-l", "-F", f'"{ident}"', f"{sha}^", "--", src)
            if not used:
                continue
            content = migration_lock.git(root, "show", f"{sha}:{path}") or ""
            if registered.get(path) != text_sha(content):
                problems.append((path, f"커밋 {sha[:10]}이 코드로 적용하던 이관 ID `{ident}`를 새 파일로 바꿈 — 엔진 출력 그대로 두고 engine-generated.json에 등록(S-MIG-11)"))
    return problems


def created_tables(sql: str, dialect: str, schema: str | None) -> dict[str, list[str]]:
    """이관 글이 만드는 테이블과 열(파티션 자식은 부모 열을 받으므로 뺌). 설계서 대조(data_classes.py)가 씀."""
    lint = FileLint("", sqltext.split(sql), dialect, schema, outside_transaction(sql))
    lint.run()
    tables = {name: list(info.columns) for name, info in lint.created.items() if not info.is_partition}
    for name, columns in lint.added.items():
        tables.setdefault(name, []).extend(c for c in columns if c not in tables.get(name, []))
    return tables


def partitioned_parents(sql: str, schema: str | None) -> list[str]:
    """이관 글이 만드는 파티션 부모 표(`PARTITION BY`)."""
    lint = FileLint("", sqltext.split(sql), "postgres", schema, outside_transaction(sql))
    lint.run()
    return [name for name, info in lint.created.items() if info.partitioned]


PARTITIONED_CALL = re.compile(r"PartitionedTable::monthly\(")
STR_CONST = re.compile(r"\bconst\s+([A-Z][A-Z0-9_]*)\s*:\s*&(?:'static\s+)?str\s*=\s*\"([^\"]*)\"\s*;")
PARTITIONED_LIST = re.compile(r"\bconst\s+PARTITIONED\s*:[^=]*=\s*&\[(.*?)\]\s*;", re.S)


def registered_partitions(text: str) -> set[str]:
    """`PartitionedTable::monthly(…)` 첫 인자로 엔진에 넘긴 표 이름(주석은 뺀 글). 인정하는 모양: 글자(`"표"`), `&str` 상수 이름,
    또는 `const PARTITIONED: &[…] = &[…]`(그 안의 글자 모두, 반복문으로 넘길 때). 그 밖의 모양은 검사가 따라가지 못하므로 쓰지 않는다."""
    if ".partitioned(" not in text:
        return set()
    consts = dict(STR_CONST.findall(text))
    names: set[str] = set()
    for m in PARTITIONED_CALL.finditer(text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
        args = text[m.end():i - 1]
        names.update(re.findall(r"\"([^\"]*)\"", args))
        names.update(consts[ident] for ident in re.findall(r"\b[A-Z][A-Z0-9_]*\b", args) if ident in consts)
        if re.search(r"\bPARTITIONED\b", text[:m.start()]) or "PARTITIONED" in args:
            listed = PARTITIONED_LIST.search(text)
            if listed:
                names.update(re.findall(r"\"([^\"]*)\"", listed.group(1)))
    return names


def lint_partitioned(root: Path) -> list[Finding]:
    """S-PART-3: 서비스 이관이 만든 파티션 부모는 모두 서비스 코드가 엔진 이관기에 `partitioned(PartitionedTable::monthly(…))`로
    적어야 한다(E-DB-5). 안 적으면 아무도 달 파티션을 만들지 않아 기본 파티션 없는 표(S-PART-2)에 쓰기가 막힌다."""
    findings: list[Finding] = []
    for directory in migration_dirs(root):
        rel_dir = directory.relative_to(root)
        if any("clickhouse" in part for part in rel_dir.parts):
            continue
        schema = default_schema(rel_dir)
        parents: set[str] = set()
        plain: dict[str, str] = {}
        for path in sorted(directory.glob("*.sql")):
            text = path.read_text(encoding="utf-8")
            parents.update(partitioned_parents(text, schema))
            for table in created_tables(text, "postgres", schema):
                plain.setdefault(table, path.relative_to(root).as_posix())
        registered: set[str] = set()
        for path in walk(directory.parent / "src", lambda name: name.endswith(".rs")):
            registered |= registered_partitions(strip_rust_comments(path.read_text(encoding="utf-8")))
        for path in sorted(directory.glob("*.sql")):
            for table in partitioned_parents(path.read_text(encoding="utf-8"), schema):
                if table not in registered:
                    findings.append(Finding(
                        path.relative_to(root).as_posix(), 1, "S-PART-3",
                        f"파티션 부모 `{table}`을 서비스 코드가 엔진 `partitioned(PartitionedTable::monthly(…))`로 적지 않음(E-DB-5)",
                    ))
        # 엔진은 `<부모>_YYYYMM` 이름만 보고 기한 지난 달을 떼어 지우므로, 그 이름의 다른 표를 두지 않는다(QA f4753d1 낮음).
        for table, rel in sorted(plain.items()):
            for parent in sorted(parents | registered):
                if table != parent and re.fullmatch(rf"{re.escape(parent)}_\d{{6}}", table):
                    findings.append(Finding(rel, 1, "S-PART-3", f"`{table}`은 엔진 달 파티션 이름(`{parent}_YYYYMM`)과 겹침 — 엔진이 기한 지난 달로 보고 지울 수 있음"))
    return findings


def header_lines(sql: str) -> list[str]:
    """엔진 이관기(`migrate.rs` `header`)의 머리: 줄마다 앞뒤 공백을 빼고, 앞쪽 빈 줄을 건너뛴 뒤 `--`로 시작하는 줄이 이어지는 동안."""
    lines = [line.strip() for line in sql.replace("\r\n", "\n").split("\n")]
    out: list[str] = []
    started = False
    for line in lines:
        if not started and not line:
            continue
        started = True
        if not line.startswith("--"):
            break
        out.append(line)
    return out


def outside_transaction(sql: str) -> bool:
    """엔진 `outside_transaction`과 같은 판정: 머리 안 어디든 `-- mookko:transaction off`."""
    return "-- mookko:transaction off" in header_lines(sql)


def owning_service(rel_dir: Path) -> str | None:
    """이관 폴더의 서비스(설계서·실행 파일을 찾는 이름)."""
    parts = rel_dir.parts
    if len(parts) >= 4 and parts[0] == "crates" and parts[1] == "services" and parts[-1] == "migrations":
        return parts[2]
    return None


def is_key_dir(rel_dir: Path) -> bool:
    """키 DB 이관 폴더 `crates/services/<서비스>/keys/migrations`(키 파기용 키 표, database.md §9.8)."""
    parts = rel_dir.parts
    return len(parts) == 5 and parts[:2] == ("crates", "services") and parts[3:] == ("keys", "migrations")


def default_schema(rel_dir: Path) -> str | None:
    service = owning_service(rel_dir)
    return f"{service}_keys" if service and is_key_dir(rel_dir) else service


WRAPPED_KEY_COLUMN = re.compile(r"(?:^|_)wrapped_key$")


def key_table_findings(rel: str, rel_dir: Path, lint: "FileLint") -> list[Finding]:
    """S-SEC-10: 감싼 행 키(`RowKeys::create`의 `WrappedKey`) 열은 키 DB에만 두고, 키 DB에는 키 표만 둔다.
    서비스 DB에 두면 그 백업(돈 DB는 월말 전체를 몇 년)에 감싼 키가 남아 KEK로 다시 풀 수 있어 키 파기가 되지 않고,
    키 DB에 다른 표를 두면 짧은 백업 보관 때문에 그 표가 복구 범위에서 먼저 사라진다."""
    findings: list[Finding] = []
    key_dir = is_key_dir(rel_dir)
    columns = [(t, info.line, c, ctype) for t, info in lint.created.items() for c, ctype in info.columns.items()]
    columns += [(t, 1, c, None) for t, added in lint.added.items() for c in added]
    if not key_dir:
        for table, line, column, _ in columns:
            if WRAPPED_KEY_COLUMN.search(column):
                findings.append(Finding(rel, line, "S-SEC-10", f"감싼 행 키 열 `{table}.{column}`은 키 DB 이관(`crates/services/<서비스>/keys/migrations/`)에만 둠 — 서비스 DB 백업에 남으면 키 파기가 되지 않음"))
        return findings
    for table, info in lint.created.items():
        kind = info.columns.get("wrapped_key")
        if kind is None:
            findings.append(Finding(rel, info.line, "S-SEC-10", f"키 DB에는 키 표(`wrapped_key bytea` 열)만 둠 — `{table}`은 서비스 DB로"))
        elif kind != "bytea":
            findings.append(Finding(rel, info.line, "S-SEC-10", f"`{table}.wrapped_key` 형식 `{kind}` — `bytea`(`WrappedKey::to_bytes`)"))
    return findings


NOT_VALID_ADD = re.compile(rf"\bADD\s+CONSTRAINT\s+({IDENT})\b[^;]*?\bNOT\s+VALID\b", re.I | re.S)
VALIDATE_STMT = re.compile(rf"^ALTER\s+TABLE\s+(?:ONLY\s+)?{QNAME}\s+VALIDATE\s+CONSTRAINT\s+({IDENT})\s*$", re.I)


def validate_only(text: str) -> set[str] | None:
    """`migrate` 파일이 `SET LOCAL …` 말고 `ALTER TABLE … VALIDATE CONSTRAINT`만 하면 그 제약 이름들, 아니면 None."""
    script = sqltext.split(text)
    if (script.directives.get("phase") or [None])[0] != "migrate":
        return None
    names: set[str] = set()
    for st in script.statements:
        if re.match(r"^SET\s+LOCAL\b", st.text, re.I):
            continue
        m = VALIDATE_STMT.match(st.text)
        if not m:
            return None
        names.add(parse_qname(m.group(1))[1])
    return names or None


def service_doc_lines(root: Path, service: str | None) -> list[str]:
    """서비스 설계서(`crates/services/<서비스>/docs/*.md`, `docs/spec/<서비스>/*.md`)의 줄."""
    if not service:
        return []
    lines: list[str] = []
    for base in (root / "crates" / "services" / service / "docs", root / "docs" / "spec" / service):
        for path in walk(base, lambda name: name.endswith(".md")):
            lines += path.read_text(encoding="utf-8").splitlines()
    return lines


def validate_deploy_findings(root: Path, directory: Path) -> list[Finding]:
    """S-MIG-4 예외(같은 배포의 VALIDATE): 바로 앞 `expand` 파일이 `NOT VALID`로 건 제약을 `VALIDATE`만 하는 `migrate` 파일은
    어느 배포에 싣는지와 근거를 적는다 — 파일 머리 `-- mookko:validate-deploy same <옛 판이 어길 수 없는 이유>`(또는 `next`),
    아니면 서비스 설계서 이관 표에서 그 파일 이름이 있는 줄에 "같은 배포"(이유와 함께)나 "다음 배포". 커밋한 이관은 고칠 수
    없으므로(S-MIG-1) 설계서 줄로도 받는다."""
    findings: list[Finding] = []
    files = sorted(p for p in directory.glob("*.sql") if FILE_NAME.match(p.name))
    doc_lines = service_doc_lines(root, owning_service(directory.relative_to(root)))
    for prev, path in zip(files, files[1:]):
        text = path.read_text(encoding="utf-8")
        names = validate_only(text)
        if not names:
            continue
        prev_text = prev.read_text(encoding="utf-8")
        if (sqltext.split(prev_text).directives.get("phase") or [None])[0] != "expand":
            continue
        added = {parse_qname(m.group(1))[1] for m in NOT_VALID_ADD.finditer(strip_sql_comments(prev_text))}
        if not names & added:
            continue
        rel = path.relative_to(root).as_posix()
        directive = sqltext.split(text).directives.get("validate-deploy")
        if directive:
            value, line = directive
            if value == "next" or (value.startswith("same ") and value[5:].strip()):
                continue
            findings.append(Finding(rel, line, "S-MIG-4", "`-- mookko:validate-deploy`는 `next` 또는 `same <옛 판이 어길 수 없는 이유>`"))
            continue
        stem = path.stem
        if any(stem in line and ("같은 배포" in line or "다음 배포" in line) for line in doc_lines):
            continue
        findings.append(Finding(
            rel, 1, "S-MIG-4",
            f"바로 앞 넓히기 `{prev.name}`의 NOT VALID 제약({', '.join(sorted(names & added))})을 VALIDATE만 함 — 같은 배포에 실으면 근거를, "
            "아니면 다음 배포라고 적음(머리 `-- mookko:validate-deploy same <이유>|next` 또는 설계서 이관 표의 이 파일 줄)",
        ))
    return findings


def lint_dir(root: Path, directory: Path) -> list[Finding]:
    """`migrations/` 폴더 하나: 파일 이름·번호 + 파일마다 판정."""
    registry = json.loads(ENGINE_GENERATED.read_text(encoding="utf-8"))
    rel_dir = directory.relative_to(root)
    dialect = "clickhouse" if any("clickhouse" in p for p in rel_dir.parts) else "postgres"
    findings: list[Finding] = []
    numbers: list[int] = []
    for path in sorted(directory.iterdir()):
        rel = path.relative_to(root).as_posix()
        if path.is_dir() or path.name == "README.md":
            continue
        match = FILE_NAME.match(path.name)
        if not match:
            findings.append(Finding(rel, 1, "S-MIG-1", "이관 파일 이름은 `NNNN_snake_설명.sql`"))
            continue
        numbers.append(int(match.group(1)))
        text = path.read_text(encoding="utf-8")
        schema = default_schema(rel_dir)
        override = sqltext.split(text).directives.get("schema")
        if override:
            schema = override[0]
        fixed, problem = engine_fixed_status(rel, text, registry)
        if problem:
            findings.append(Finding(rel, 1, "S-MIG-1", problem))
        lint = FileLint(rel, sqltext.split(text), dialect, schema, outside_transaction(text), fixed)
        findings += lint.run()
        if dialect == "postgres":
            findings += key_table_findings(rel, rel_dir, lint)
    if dialect == "postgres":
        findings += validate_deploy_findings(root, directory)
    for expected, actual in enumerate(sorted(numbers), start=1):
        if expected != actual:
            findings.append(Finding(rel_dir.as_posix(), 1, "S-MIG-1", f"번호가 0001부터 빠짐없이 이어지지 않음(기대 {expected:04d}, 실제 {actual:04d})"))
            break
    return findings


CHAR_LITERAL = re.compile(r"'(?:\\(?:x[0-9a-fA-F]{2}|u\{[0-9a-fA-F]+\}|.)|[^'\\\n])'")
RAW_START = re.compile(r'b?r(#*)"')


def strip_rust_comments(text: str) -> str:
    """Rust 주석(`// …`, 겹칠 수 있는 `/* … */`)을 공백으로 바꾼다(줄 수는 그대로). 문자열(`"…"`, `r#"…"#`) 안의 `//`는 그대로 둔다.
    코드 모양을 보는 검사(파티션 등록·읽기 계정·고정 파일)가 주석에 적은 호출을 세지 않게(QA f4753d1 낮음)."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif text.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif text.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            out.append("".join("\n" if ch == "\n" else " " for ch in text[i:j]))
            i = j
        elif c == "r" and re.match(r'r#*"', text[i:i + 8]) and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            hashes = len(re.match(r"r(#*)", text[i:]).group(1))
            end = text.find('"' + "#" * hashes, i + 2 + hashes)
            j = n if end < 0 else end + 1 + hashes
            out.append(text[i:j])
            i = j
        elif c == "'" and CHAR_LITERAL.match(text, i):
            m = CHAR_LITERAL.match(text, i)
            out.append(m.group(0))  # 문자 리터럴(`'"'`)을 문자열 시작으로 읽지 않게
            i = m.end()
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def rust_strings(text: str) -> list[tuple[int, str]]:
    """Rust 소스의 문자열 리터럴(시작 위치, 내용). 주석·문자 리터럴은 건너뛴다."""
    out: list[tuple[int, str]] = []
    n = len(text)
    i = 0
    while i < n:
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif text.startswith("/*", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if text.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif text.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
        elif (raw := RAW_START.match(text, i)) and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            close = '"' + raw.group(1)
            end = text.find(close, raw.end())
            end = n if end < 0 else end
            out.append((i, text[raw.end() : end]))
            i = end + len(close)
        elif text[i] == '"' or (text[i] == "b" and text.startswith('b"', i) and (i == 0 or not text[i - 1].isalnum())):
            start = i
            i += 2 if text[i] == "b" else 1
            body: list[str] = []
            while i < n and text[i] != '"':
                if text[i] == "\\":
                    # `\n` 이스케이프는 줄바꿈으로 살림(SQL `--` 주석이 다음 줄까지 먹지 않게), 나머지 이스케이프는 공백.
                    body.append("\n" if text[i + 1 : i + 2] == "n" else " ")
                    i += 2
                    continue
                body.append(text[i])
                i += 1
            out.append((start, "".join(body)))
            i += 1
        elif text[i] == "'":
            lit = CHAR_LITERAL.match(text, i)
            i = lit.end() if lit else i + 1
        else:
            i += 1
    return out


EMBEDDED = re.compile(
    r'\(\s*"(?P<id>[^"]+)"\s*,\s*include_str!\(\s*"(?P<path>[^"]*migrations/(?P<file>[^"/]+)\.sql)"\s*\)\s*,?\s*\)', re.S
)


def lint_embedded(root: Path, registry: dict | None = None) -> list[Finding]:
    """서비스가 이관을 실행 파일에 넣어(`include_str!` + `SchemaMigrator::add`) 쓰는 경우(S-MIG-10, S-MONEY-2):
    - 코드의 이관 ID는 파일 이름(`.sql` 뺀 것)과 같고, 폴더의 이관 파일은 모두 한 번씩 들어 있어야 함(빠지거나 남는 파일 없음).
    - `.add()`는 늘 트랜잭션 안에서 돌리므로 첫 줄이 `-- mookko:transaction off`인 파일은 넣을 수 없음(엔진 `add_dir`·도우미 필요, E-DB-13).
    - 이관이 만드는 덧붙이기만 표(이름에 ledger·journal·audit, `_head(s)` 제외)는 서비스 코드가 `append_only`로 지정해야 함
      (엔진 `grant`가 지정 안 된 표에 UPDATE·DELETE를 줌). 표 이름 글자와 `append_only`가 crate 소스에 있는지로 본다."""
    findings: list[Finding] = []
    if registry is None:
        registry = json.loads(ENGINE_GENERATED.read_text(encoding="utf-8"))
    services = root / "crates" / "services"
    if not services.is_dir():
        return findings
    for crate in sorted(p for p in services.iterdir() if (p / "migrations").is_dir()):
        sources = walk(crate / "src", lambda name: name.endswith(".rs"))
        text_by_file = {p: p.read_text(encoding="utf-8") for p in sources}
        all_text = "\n".join(text_by_file.values())
        files = {p.name: p for p in sorted((crate / "migrations").glob("*.sql"))}
        embedded: dict[str, tuple[Path, int, str]] = {}
        for path, text in text_by_file.items():
            for m in EMBEDDED.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                rel = path.relative_to(root).as_posix()
                name = f"{m.group('file')}.sql"
                if m.group("id") != m.group("file"):
                    findings.append(Finding(rel, line, "S-MIG-10", f"이관 ID `{m.group('id')}`가 파일 이름 `{name}`과 다름(파일 이름이 이관 ID)"))
                if name in embedded:
                    findings.append(Finding(rel, line, "S-MIG-10", f"`{name}`을 두 번 넣음"))
                embedded[name] = (path, line, m.group("id"))
        if embedded:
            for name in sorted(set(files) - set(embedded)):
                rel = files[name].relative_to(root).as_posix()
                if engine_fixed_status(rel, files[name].read_text(encoding="utf-8"), registry)[0]:
                    continue  # 엔진 생성 고정 파일: 코드가 엔진 함수로 같은 글을 만들어 적용함(S-MIG-11)
                findings.append(Finding(rel, 1, "S-MIG-10", "코드의 이관 목록(include_str)에 이 파일이 없음 — 적용되지 않음"))
            for name in sorted(set(embedded) - set(files)):
                path, line, _ = embedded[name]
                findings.append(Finding(path.relative_to(root).as_posix(), line, "S-MIG-10", f"`migrations/{name}` 파일이 없음"))
            # 넣은 글을 판정해 `add_concurrent_index`로 보내는 서비스는 transaction off 파일을 넣어도 됨(그 분기 자체는 [QA]).
            # 엔진 도우미가 머리를 보고 트랜잭션 밖으로 보냄: add_embedded·add_generated(E-DB-13·14), 손으로 고르면 add_concurrent_index.
            routes_concurrent = any(f"{name}(" in all_text for name in ("add_concurrent_index", "add_embedded", "add_generated"))
            for name in sorted(set(embedded) & set(files)):
                if routes_concurrent:
                    break
                if outside_transaction(files[name].read_text(encoding="utf-8")):
                    path, line, _ = embedded[name]
                    findings.append(
                        Finding(
                            path.relative_to(root).as_posix(),
                            line,
                            "S-MIG-10",
                            f"`{name}`은 transaction off인데 include_str + `.add()`는 트랜잭션 안에서 돌림 — `add_concurrent_index` 또는 엔진 도우미(E-DB-13)",
                        )
                    )
        schema = crate.name
        for path in files.values():
            for table in created_tables(path.read_text(encoding="utf-8"), "postgres", schema):
                if APPEND_ONLY.search(table) and (f'"{table}"' not in all_text or "append_only" not in all_text):
                    findings.append(
                        Finding(path.relative_to(root).as_posix(), 1, "S-MONEY-2", f"덧붙이기만 하는 `{table}`을 서비스 이관기에서 `append_only`로 지정하지 않음(엔진 grant가 UPDATE·DELETE를 줌)")
                    )
    return findings


EXCEPTIONS = Path(__file__).resolve().parent / "exceptions.json"
# SQL 문장 머리(문자열 처음이나 `;` 뒤)에 오는 DDL·권한 문장만 본다. 감사 동작 이름(`handle.revoke`)·식별자(`revoke_handle`)·
# 낱말 하나(`"grant"`)는 문장이 아니므로 잡지 않는다(links 오탐 2026-10-30). ATTACH·DETACH PARTITION은 ALTER TABLE 문장 안에 있음.
SERVICE_DDL = re.compile(
    r"(?:^|;)\s*(?:"
    r"(?:CREATE|ALTER|DROP)\s+(?:OR\s+REPLACE\s+|UNIQUE\s+|UNLOGGED\s+|TEMP(?:ORARY)?\s+|MATERIALIZED\s+)*"
    r"(?:TABLE|INDEX|SCHEMA|FUNCTION|PROCEDURE|TRIGGER|VIEW|ROLE|TYPE|EXTENSION|SEQUENCE|POLICY|DATABASE)\b"
    r"|TRUNCATE\s+(?:TABLE\s+)?[A-Za-z_\"{]"
    r"|(?:GRANT|REVOKE)\s+[A-Za-z_, ]+?\s+(?:ON|TO|FROM)\s"
    r")",
    re.I,
)


def exception_paths(registry: dict, today: datetime.date | None = None, root: Path | None = None) -> tuple[set[str], list[Finding]]:
    """기한 안의 예외 파일과, 등록부 문제(칸 빠짐·근거 문서 없음·기한 지남). gates.md waived(근거 문서 + 만료일)."""
    paths: set[str] = set()
    problems: list[Finding] = []
    for item in registry.get("exceptions", []):
        missing = [k for k in ("id", "paths", "rule", "reason", "adr", "condition", "expires", "approvedBy") if not item.get(k)]
        if missing:
            problems.append(Finding("scripts/ci/db/exceptions.json", 1, "S-BND-7", f"예외 {item.get('id')}에 {missing} 칸이 없음"))
            continue
        document = item["adr"].split()[0].rstrip(",")
        if root is not None and not (root / document).is_file():
            problems.append(Finding("scripts/ci/db/exceptions.json", 1, "S-BND-7", f"예외 {item['id']}의 근거 문서 `{document}`가 없음"))
            continue
        if datetime.date.fromisoformat(item["expires"]) < (today or datetime.date.today()):
            problems.append(Finding("scripts/ci/db/exceptions.json", 1, "S-BND-7", f"예외 {item['id']} 기한({item['expires']})이 지남 — 조건: {item['condition']}"))
            continue
        paths.update(item["paths"])
    return paths, problems


def strip_sql_comments(text: str) -> str:
    """SQL 주석(`-- …` 줄 끝까지, `/* … */`)을 지운다. 주석 줄로 시작하는 SQL 문자열의 문장 머리를 보려고(QA 1d41835 낮음).
    문자열 값 안의 `--`까지 가릴 수는 있지만, 그러면 검사가 더 잡는 쪽(DDL이 문장 머리로 드러남)이라 닫힌 쪽이다."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"--[^\n]*", " ", text)


def lint_service_ddl(root: Path, registry: dict) -> list[Finding]:
    """서비스·실행 파일 crate(`crates/services/*/src`, `crates/apps/*/src`) Rust 문자열 안의 DDL·권한 문장(S-BND-7).
    DDL은 이관 파일과 엔진 유지보수 작업(엔진 crate)만 — 서비스나 실행 파일이 구조를 바꾸면 이관 검사·적용 시험·설계서 대조를
    모두 비켜 간다(운영툴이 파티션 DDL을 apps로 옮긴 일, QA 6b7fdfe). 기한 있는 예외는 exceptions.json."""
    allowed, findings = exception_paths(registry, root=root)
    sources: list[Path] = []
    for base in (root / "crates" / "services", root / "crates" / "apps"):
        sources += [p for p in walk(base, lambda name: name.endswith(".rs")) if "src" in p.relative_to(base).parts]
    for path in sources:
        rel = path.relative_to(root).as_posix()
        if rel in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        for start, body in rust_strings(text):
            flat = " ".join(strip_sql_comments(body).split())
            if SERVICE_DDL.search(flat):
                findings.append(Finding(rel, text.count("\n", 0, start) + 1, "S-BND-7", "서비스 코드의 DDL·권한 문장 금지 — 이관 파일(migrations/)이나 엔진 유지보수 작업으로(기한 있는 예외는 exceptions.json)"))
    return findings


def lint_rust(root: Path) -> tuple[list[Finding], int]:
    """Rust 문자열 안의 `SELECT *`·`RETURNING *`(S-Q-2)."""
    findings: list[Finding] = []
    count = 0
    base = root / "crates"
    if not base.exists():
        return findings, 0
    for path in walk(base, lambda name: name.endswith(".rs")):
        rel_path = path.relative_to(root)
        count += 1
        text = path.read_text(encoding="utf-8")
        for start, body in rust_strings(text):
            flat = " ".join(body.split())
            if re.search(r"\b(SELECT|RETURNING)\b", flat, re.I) and (SELECT_STAR.search(flat) or RETURNING_STAR.search(flat)):
                line = text.count("\n", 0, start) + 1
                findings.append(Finding(rel_path.as_posix(), line, "S-Q-2", "SQL 문자열에 `SELECT *`·`RETURNING *` 금지"))
    return findings, count


def walk(base: Path, want) -> list[Path]:
    """`base` 아래 파일 중 `want(이름)`인 것. 빼는 폴더(target 등)는 아예 내려가지 않는다(WSL `/mnt/c`에서 큰 폴더를 훑지 않게)."""
    out: list[Path] = []
    if not base.exists():
        return out
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        out.extend(Path(dirpath) / name for name in filenames if want(name))
    return sorted(out)


def migration_dirs(root: Path) -> list[Path]:
    dirs: list[Path] = []
    base = root / "crates"
    if not base.exists():
        return dirs
    for dirpath, dirnames, _ in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        if Path(dirpath).name == "migrations":
            dirs.append(Path(dirpath))
    return sorted(dirs)


def history_findings(root: Path, locks: dict, lock_file: Path) -> list[tuple[str, str]]:
    """git 기록으로 보는 S-MIG-1: 잠금 목록 줄이기, 출시 전 이관 다시 쓰기의 커밋 본문 표시. 기록을 못 읽으면 건너뜀(통과 아님)."""
    since = locks.get("historyCheckedSince")
    required = os.environ.get("MOOKKO_REQUIRE_GIT_HISTORY") == "1"
    if not since or lock_file.resolve() != migration_lock.LIST.resolve():
        return []  # 시험용 목록·뿌리
    commits = migration_lock.history_commits(root, since)
    versions = migration_lock.lock_versions(root, since, locks) if commits is not None else None
    if commits is None or versions is None:
        message = "git 기록을 읽을 수 없어 잠금 목록 줄이기·커밋 본문 표시 확인을 건너뜀(통과 아님)"
        if required:
            return [(migration_lock.LIST_REL, message + " — MOOKKO_REQUIRE_GIT_HISTORY=1")]
        print(f"  {message}")
        return []
    launched = {e["dir"] for e in migration_lock.entries(locks) if e.get("dir")}
    allowed = migration_lock.prelaunch_allowed(locks)
    problems: list[tuple[str, str]] = []
    registry_paths = {e.get("path") for e in json.loads(ENGINE_GENERATED.read_text(encoding="utf-8")).get("files", [])}
    for path in migration_lock.uncommitted_rewrites(root):
        if path in registry_paths:
            continue  # 엔진 생성 고정 파일(SHA는 lint_dir이 확인)
        if allowed:
            print(f"  알림: {path} — 이미 커밋한 이관을 바꿈. 커밋 본문에 `{migration_lock.REWRITE_MARK} <파일>`과 이유가 있어야 CI가 통과")
        else:
            problems.append((path, "이미 커밋한 이관을 바꿈 — 출시 전 예외는 사용자 결정 전이라 쓸 수 없음, 되돌리고 새 이관 파일을 더함(S-MIG-1)"))
    registry = json.loads(ENGINE_GENERATED.read_text(encoding="utf-8"))
    exempt = frozenset(
        e["path"] for e in registry.get("files", [])
        if (root / e.get("path", "")).is_file() and engine_fixed_status(e["path"], (root / e["path"]).read_text(encoding="utf-8"), registry)[0]
    )
    code_since = locks.get("codeIdCheckSince")
    if code_since:
        problems += code_id_to_file_findings(root, code_since) or []
    return problems + migration_lock.shrink_findings(versions) + migration_lock.rewrite_findings(commits, launched, allowed, exempt)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="검사할 저장소 뿌리(시험용)")
    parser.add_argument("--pending", type=Path, default=pending.LIST, help="기한부 유예 목록(시험용)")
    parser.add_argument("--lock-file", type=Path, default=migration_lock.LIST, help="이관 잠금 목록(시험용)")
    parser.add_argument("--exceptions", type=Path, default=EXCEPTIONS, help="기한 있는 예외 등록부(시험용)")
    parser.add_argument("--engine-generated", type=Path, default=ENGINE_GENERATED, help="엔진 생성 고정 파일 등록부(시험용)")
    parser.add_argument("--lock", metavar="DIR", help="출시: 이 이관 폴더(저장소 기준)의 지금 파일을 잠금 목록에 적음")
    parser.add_argument("--decided-by", help="--lock: 출시 결정 근거(예: 사용자 결정 2026-11-20)")
    parser.add_argument("--launched-at", type=datetime.date.fromisoformat, help="--lock: 출시 날짜 YYYY-MM-DD")
    parser.add_argument("--schema", help="--lock: 운영 스키마 이름(기본은 서비스 이름, 엔진 SHA 계산에 씀)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    locks = migration_lock.load(args.lock_file)
    if args.lock:
        if not args.decided_by or not args.launched_at:
            print("--lock에는 --decided-by와 --launched-at이 필요합니다")
            return 2
        rel_dir = args.lock.rstrip("/")
        schema = args.schema or default_schema(Path(rel_dir))
        if not schema:
            print("--lock 폴더의 스키마를 정할 수 없음 — --schema <이름>")
            return 2
        updated = migration_lock.record(root, locks, rel_dir, schema, args.decided_by, args.launched_at)
        args.lock_file.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"locked {args.lock} in {args.lock_file.name}")
        return 0
    problems: list[str] = []
    waivers = pending.load(problems, args.pending)
    findings: list[Finding] = []
    dirs = migration_dirs(root)
    files = 0
    for directory in dirs:
        files += sum(1 for p in directory.iterdir() if p.suffix == ".sql")
        findings += lint_dir(root, directory)
    rust_findings, rust_files = lint_rust(root)
    rust_findings += lint_embedded(root)
    rust_findings += lint_service_ddl(root, json.loads(args.exceptions.read_text(encoding="utf-8")))
    rust_findings += engine_fixed_tests(root, json.loads(args.engine_generated.read_text(encoding="utf-8")))
    rust_findings += lint_partitioned(root)
    findings += rust_findings
    failing = [f for f in findings if not pending.is_waived(pending.match(waivers, f.path, f.rule))]
    waived = [f for f in findings if f not in failing]
    # 잠금 위반은 유예하지 않음(출시 뒤 이관 다시 쓰기).
    failing += [Finding(path, 1, "S-MIG-1", message) for path, message in migration_lock.check(root, locks)]
    failing += [Finding(path, 1, "S-MIG-1", message) for path, message in history_findings(root, locks, args.lock_file)]
    for f in waived:
        item = pending.match(waivers, f.path, f.rule)
        print(f"  유예({item.owner}, {item.until} 까지): {f}" if item else f"  유예: {f}")
    if failing or problems:
        print(f"migration lint failed ({len(failing) + len(problems)}):")
        for line in problems:
            print(f"  - {line}")
        for f in failing:
            print(f"  - {f}")
        return 1
    locked = len(migration_lock.entries(locks))
    print(f"migration lint passed ({len(dirs)} dirs, {files} migrations, {rust_files} rust files, 유예 {len(waived)}, 출시 잠금 {locked} dirs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

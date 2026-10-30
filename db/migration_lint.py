"""이관 파일 검사 (docs/policy/conventions/sql.md, docs/architecture/database.md §7).

라이브 패치 동안 신구 판이 같은 DB를 쓰므로, 긴 잠금·다시 쓰기·옛 판을 깨는 변경이 이관에 들어오지 못하게 막는다.
- `crates/**/migrations/*.sql`을 읽는다(경로에 `clickhouse`가 들면 ClickHouse 규칙, 아니면 PostgreSQL 규칙).
- Rust 소스(`crates/**/*.rs`)의 문자열 안 `SELECT *`·`RETURNING *`도 찾는다(S-Q-2).
- 판정은 규칙 번호(S-*)와 함께 `파일:줄`로 알린다. 하나라도 있으면 종료 코드 1.
완전한 SQL 파서가 아니라 정해진 모양을 찾는 검사다. 잡지 못하는 것은 실제 적용 시험(migration_apply.py)과 QA가 본다.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pending  # noqa: E402
import sqltext  # noqa: E402
from sqltext import IDENT, QNAME, parse_qname, paren_body, split_top_level  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist"}
FILE_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
PHASES = {"expand", "migrate", "contract"}
KNOWN_DIRECTIVES = {"phase", "transaction", "schema"}
# 덧붙이기만 하는 표(이름에 ledger·journal·audit). 사슬·구간 머리(`…_head`, `…_heads`)는 지금 상태를 고쳐 쓰는 표라 뺀다.
APPEND_ONLY = re.compile(r"^(?!.*_heads?$).*(ledger|journal|audit)")
AMOUNT_NAME = re.compile(r"(^|_)(amount|balance|price|fee)s?($|_)|_minor$")
VOLATILE = re.compile(
    r"\b(clock_timestamp|random|gen_random_uuid|uuidv4|uuidv7|uuid_generate_v\d\w*|timeofday|nextval|"
    r"txid_current|pg_current_xact_id)\s*\(",
    re.I,
)
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


class FileLint:
    """이관 파일 하나의 판정."""

    def __init__(self, rel: str, script: sqltext.Script, dialect: str, schema: str | None) -> None:
        self.rel = rel
        self.script = script
        self.dialect = dialect
        self.schema = schema
        self.findings: list[Finding] = []
        self.created: dict[str, TableInfo] = {}
        self.triggers: dict[str, set[str]] = {}
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
                self.add(line, "S-MIG-4", f"모르는 머리 지시 `mookko:{name}`(phase·transaction·schema만)")
        for name, line in self.script.duplicate_directives:
            self.add(line, "S-MIG-4", f"머리 지시 `mookko:{name}`가 두 번")
        for line in self.script.late_directives:
            self.add(line, "S-MIG-4", "`-- mookko:` 지시는 첫 문장 앞 머리에만")
        if self.phase is None:
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
        if '"' in t:
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
        allowed = {f"{self.schema}_{suffix}" for suffix in ("app", "ro", "recon", "maint")}
        grantees = [parse_qname(g)[1] for g in to.group(1).split(",")] if to else []
        for grantee in grantees:
            if grantee != "public" and grantee not in allowed:
                self.add(st.line, "S-BND-5", f"`{grantee}`에게 GRANT: 자기 서비스 계정({', '.join(sorted(allowed))})만")
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
        if re.match(r"^DISABLE\s+TRIGGER\b", a, re.I) and APPEND_ONLY.search(table):
            self.add(line, "S-MONEY-2", f"덧붙이기만 하는 `{table}`의 막기 트리거를 끌 수 없음")
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
            if self.phase == "contract":
                self.add(line, "S-MIG-4", "contract 파일에 ADD COLUMN(넓히기)을 섞지 않음")
            if existing:
                default = re.search(r"\bDEFAULT\s+(.*?)(?:\s+(?:NOT\s+NULL|NULL|CONSTRAINT|CHECK|REFERENCES|UNIQUE|PRIMARY)\b|$)", body, IS)
                if (default and VOLATILE.search(default.group(1))) or re.search(r"\bGENERATED\b.*\bSTORED\b|\bGENERATED\s+(ALWAYS|BY\s+DEFAULT)\s+AS\s+IDENTITY\b", body, IS) or re.fullmatch(r"(small|big)?serial[248]?", ctype.lower()):
                    self.add(line, "S-MIG-2b", f"`{table}.{cname}`: 휘발 기본값·STORED·identity·serial 열 추가는 테이블을 다시 씀")
                elif re.search(r"\bNOT\s+NULL\b", body, re.I) and not default:
                    self.add(line, "S-MIG-2c", f"`{table}.{cname}`: NOT NULL 열은 상수 기본값과 함께만(아니면 NULL로 넓히고 나중에 굳힘)")
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
        if re.match(r"^ALTER\s+(VIEW|MATERIALIZED\s+VIEW|SCHEMA|FUNCTION|PROCEDURE|SEQUENCE|TYPE)\b.*\b(RENAME|SET\s+SCHEMA)\b", t, re.I):
            self.add(line, "S-MIG-4", "이름 바꾸기 금지(옛 판이 깨짐)")
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
        if len(stmts) != 1:
            self.add(1, "S-MIG-6", f"transaction off 파일에는 문장 하나만(지금 {len(stmts)}개)")
        for st in stmts:
            if not re.search(r"\bCONCURRENTLY\b", st.text, re.I):
                self.add(st.line, "S-MIG-6", "transaction off 파일은 CONCURRENTLY 문장만")
            if not re.search(r"\bIF\s+(NOT\s+)?EXISTS\b", st.text, re.I) and not re.match(r"^(REINDEX|ALTER\s+TABLE)\b", st.text, re.I):
                self.add(st.line, "S-MIG-6", "다시 해도 안전하게 `IF NOT EXISTS`·`IF EXISTS`")

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


def lint_text(rel: str, sql: str, dialect: str, schema: str | None) -> list[Finding]:
    """이관 SQL 글 하나를 판정한다(시험이 직접 부름)."""
    return FileLint(rel, sqltext.split(sql), dialect, schema).run()


def default_schema(rel_dir: Path) -> str | None:
    parts = rel_dir.parts
    if len(parts) >= 4 and parts[0] == "crates" and parts[1] == "services" and parts[-1] == "migrations":
        return parts[2]
    return None


def lint_dir(root: Path, directory: Path) -> list[Finding]:
    """`migrations/` 폴더 하나: 파일 이름·번호 + 파일마다 판정."""
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
        findings += lint_text(rel, text, dialect, schema)
    for expected, actual in enumerate(sorted(numbers), start=1):
        if expected != actual:
            findings.append(Finding(rel_dir.as_posix(), 1, "S-MIG-1", f"번호가 0001부터 빠짐없이 이어지지 않음(기대 {expected:04d}, 실제 {actual:04d})"))
            break
    return findings


CHAR_LITERAL = re.compile(r"'(?:\\(?:x[0-9a-fA-F]{2}|u\{[0-9a-fA-F]+\}|.)|[^'\\\n])'")
RAW_START = re.compile(r'b?r(#*)"')


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
                    body.append(" ")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="검사할 저장소 뿌리(시험용)")
    parser.add_argument("--pending", type=Path, default=pending.LIST, help="기한부 유예 목록(시험용)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    problems: list[str] = []
    waivers = pending.load(problems, args.pending)
    findings: list[Finding] = []
    dirs = migration_dirs(root)
    files = 0
    for directory in dirs:
        files += sum(1 for p in directory.iterdir() if p.suffix == ".sql")
        findings += lint_dir(root, directory)
    rust_findings, rust_files = lint_rust(root)
    findings += rust_findings
    failing = [f for f in findings if not pending.is_waived(pending.match(waivers, f.path))]
    waived = [f for f in findings if f not in failing]
    for f in waived:
        item = pending.match(waivers, f.path)
        print(f"  유예({item.owner}, {item.until} 까지): {f}" if item else f"  유예: {f}")
    if failing or problems:
        print(f"migration lint failed ({len(failing) + len(problems)}):")
        for line in problems:
            print(f"  - {line}")
        for f in failing:
            print(f"  - {f}")
        return 1
    print(f"migration lint passed ({len(dirs)} dirs, {files} migrations, {rust_files} rust files, 유예 {len(waived)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

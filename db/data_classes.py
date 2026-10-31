"""설계서 데이터 등급 검사 (docs/policy/conventions/sql.md §6·§11, docs/architecture/database.md §9).

모든 테이블의 모든 열에 데이터 등급과 보호 방법이 적혀 있어야, 개인정보·비밀값이 평문으로 DB·백업·로그에 남는 일을
설계 단계에서 막을 수 있다. `crates/**/docs/data-model.md`와 `docs/spec/**/data-model.md`를 읽어 판정한다.
- 열 표(머리에 `열`·`형식`이 있는 표)에는 `등급`·`보호` 칸이 있어야 하고, 값은 정해진 것만(S-SEC-1).
- 등급마다 쓸 수 있는 보호만(S-SEC-2), 이름이 비밀값·개인정보처럼 보이면 그 등급 이상(S-SEC-2).
- `암호+색인` 열은 같은 테이블에 `<열>_bidx`·`<열>_bidx_kid`, 그 둘은 원래 열이 `암호+색인`일 때만(S-SEC-3).
- SQL 블록의 `CREATE TABLE` 열은 모두 등급 표에 있어야 함(S-SEC-1), 테이블 절마다 `보관`(S-SEC-6).
- 감싼 행 키 열(`wrapped_key`)은 `비밀`·`암호`(S-SEC-10).
- `열(요약)`처럼 열을 한 칸에 몰아 적은 표는 열마다 등급을 적을 수 없으므로 실패(S-SEC-1).
pending.json에 기한과 함께 오른 설계서는 기한까지 경고만.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import migration_lint  # noqa: E402
import pending  # noqa: E402
import sqltext  # noqa: E402
from sqltext import IDENT, QNAME, paren_body, parse_qname, split_top_level  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist"}

ALLOWED: dict[str, set[str]] = {
    "공개": {"평문", "암호", "암호+색인", "해시", "토큰화", "참조"},
    "내부": {"평문", "암호", "암호+색인", "해시", "토큰화", "참조"},
    "개인": {"암호", "암호+색인", "해시"},
    "민감": {"암호", "암호+색인", "토큰화"},
    "비밀": {"해시", "암호", "참조"},
}
PROTECTIONS = {"평문", "암호", "암호+색인", "해시", "토큰화", "참조"}
RANK = {"공개": 0, "내부": 1, "개인": 2, "민감": 3, "비밀": 4}
SECRET_NAME = re.compile(r"password|passwd|secret|(^|_)tokens?($|_)|api_?key|private_?key|totp|recovery_?code|mnemonic")
PERSONAL_NAME = re.compile(
    r"e_?mail|phone|mobile|birth|(^|_)ip($|_)|ip_?addr|address_line|street|postal|zip_?code|real_name|legal_name|full_name|"
    r"passport|(^|_)card_?(no|num|number)|(^|_)pan($|_)|bank_?account|account_?number|(^|_)rrn($|_)|resident|(^|_)ssn($|_)|user_?agent"
)
NAME_EXCEPTION = "이름 예외"
REST = "(나머지)"


@dataclass(frozen=True)
class Problem:
    """판정 하나."""

    path: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} {self.message}"


@dataclass
class Section:
    """제목 하나 아래(다음 제목 전까지)."""

    title: str
    line: int
    tables: list[str]
    level: int = 0
    text: list[str] = field(default_factory=list)


def table_names(heading: str) -> list[str]:
    """제목의 백틱 안 테이블 이름. 서비스가 정하는 이름은 `<원장>`처럼 꺾쇠 자리 표시로 쓸 수 있다(엔진 테이블)."""
    return [n.split(".")[-1] for n in re.findall(r"`((?:[A-Za-z_]|<[^>`]+>)(?:[A-Za-z0-9_.]|<[^>`]+>)*)`", heading)]


def snake(name: str) -> str:
    """`PascalCase`·`snake_case` 이름을 비교용 snake로."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def cells(row: str) -> list[str]:
    """표 한 줄의 칸(백틱 안의 `|`는 나누지 않음)."""
    out: list[str] = []
    current: list[str] = []
    in_code = False
    body = row.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    for ch in body:
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            out.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    out.append("".join(current).strip())
    return out


def ident_of(cell: str) -> str:
    """칸에서 열·테이블 이름(백틱 안 우선)."""
    code = re.findall(r"`([^`]+)`", cell)
    text = code[0] if code else cell
    return text.strip().split(".")[-1].strip()


def sections(lines: list[str]) -> list[Section]:
    out = [Section(title="", line=1, tables=[])]
    in_fence = False
    for no, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        heading = None if in_fence else re.match(r"^(#{2,6})\s+(.*)$", line)
        if heading:
            names = table_names(heading.group(2))
            out.append(Section(title=heading.group(2), line=no, tables=names, level=len(heading.group(1))))
        else:
            out[-1].text.append(line)
    return out


class DocCheck:
    """설계서 하나의 판정."""

    def __init__(self, rel: str, text: str) -> None:
        self.rel = rel
        self.lines = text.replace("\r\n", "\n").split("\n")
        self.problems: list[Problem] = []
        # 테이블 → 열 → 등급, 테이블 → (나머지) 등급
        self.classified: dict[str, dict[str, str]] = {}
        self.sql_tables: dict[str, tuple[int, list[str]]] = {}

    def add(self, line: int, rule: str, message: str) -> None:
        self.problems.append(Problem(self.rel, line, rule, message))

    def run(self) -> list[Problem]:
        current_tables: list[str] = []
        table_rows: list[tuple[int, str]] = []
        in_fence = False
        fence_lang = ""
        fence_lines: list[str] = []
        fence_start = 0
        for no, line in enumerate(self.lines, start=1):
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_fence:
                    if fence_lang == "sql":
                        self.read_sql(fence_start, "\n".join(fence_lines))
                    in_fence = False
                    fence_lines = []
                else:
                    self.flush_table(table_rows, current_tables)
                    table_rows = []
                    in_fence = True
                    fence_lang = stripped[3:].strip().lower()
                    fence_start = no
                continue
            if in_fence:
                fence_lines.append(line)
                continue
            heading = re.match(r"^(#{2,6})\s+(.*)$", line)
            if heading:
                self.flush_table(table_rows, current_tables)
                table_rows = []
                current_tables = table_names(heading.group(2))
                continue
            if stripped.startswith("|"):
                table_rows.append((no, line))
            else:
                self.flush_table(table_rows, current_tables)
                table_rows = []
        self.flush_table(table_rows, current_tables)
        self.check_sql_coverage()
        self.check_sections()
        return self.problems

    def flush_table(self, rows: list[tuple[int, str]], heading_tables: list[str]) -> None:
        if len(rows) < 2:
            return
        header = cells(rows[0][1])
        names = [h.replace(" ", "") for h in header]
        if any(n.startswith("열(") for n in names):
            self.add(rows[0][0], "S-SEC-1", "열을 한 칸에 몰아 적은 표 — 테이블마다 열 표(열·형식·등급·보호)로")
            return
        if "열" not in names:
            return
        sql_classification = "형식" not in names
        if sql_classification and "테이블" not in names:
            return
        if "등급" not in names or "보호" not in names:
            self.add(rows[0][0], "S-SEC-1", "열 표에 `등급`·`보호` 칸이 없음")
            for _, line in rows[2:]:
                row = cells(line)
                table = ident_of(row[names.index("테이블")]) if "테이블" in names and names.index("테이블") < len(row) else (heading_tables[0] if heading_tables else "")
                if table:
                    self.classified.setdefault(table, {})
            return
        col_i, grade_i, prot_i = names.index("열"), names.index("등급"), names.index("보호")
        table_i = names.index("테이블") if "테이블" in names else None
        seen: dict[str, dict[str, str]] = {}
        for no, line in rows[2:]:
            row = cells(line)
            if len(row) <= max(col_i, grade_i, prot_i):
                self.add(no, "S-SEC-1", "칸 수가 머리와 다름")
                continue
            if table_i is not None and table_i < len(row):
                table = ident_of(row[table_i])
            elif len(heading_tables) == 1:
                table = heading_tables[0]
            else:
                self.add(no, "S-SEC-1", "테이블 이름을 알 수 없음(제목에 `테이블` 하나 또는 `테이블` 칸)")
                continue
            column = REST if row[col_i].strip() == REST else ident_of(row[col_i])
            grade, prot = row[grade_i].strip(), row[prot_i].strip()
            self.check_row(no, table, column, grade, prot, NAME_EXCEPTION in line)
            seen.setdefault(table, {})[column] = prot
            self.classified.setdefault(table, {})[column] = grade
        for table, columns in seen.items():
            for column, prot in columns.items():
                if prot == "암호+색인":
                    # 엔진 `BlindIndex::compute`가 `{key_id, digest}`를 내므로 값과 키 ID 열을 함께 둠(E-DB-7).
                    for needed in (f"{column}_bidx", f"{column}_bidx_kid"):
                        if needed not in columns:
                            self.add(rows[0][0], "S-SEC-3", f"`{table}.{column}`이 암호+색인인데 `{needed}` 열이 없음")
                for suffix in ("_bidx", "_bidx_kid"):
                    base = column[: -len(suffix)]
                    if column.endswith(suffix) and columns.get(base) != "암호+색인":
                        self.add(rows[0][0], "S-SEC-3", f"`{table}.{column}`의 원래 열 `{base}`이 이 표에서 암호+색인이 아님")

    def check_row(self, line: int, table: str, column: str, grade: str, prot: str, name_exception: bool) -> None:
        where = f"`{table}.{column}`"
        if grade not in ALLOWED:
            self.add(line, "S-SEC-1", f"{where} 등급 `{grade}`: {'·'.join(ALLOWED)} 중 하나")
            return
        if prot not in PROTECTIONS:
            self.add(line, "S-SEC-1", f"{where} 보호 `{prot}`: {'·'.join(sorted(PROTECTIONS))} 중 하나")
            return
        if prot not in ALLOWED[grade]:
            self.add(line, "S-SEC-2", f"{where} 등급 `{grade}`에는 보호 {'·'.join(sorted(ALLOWED[grade]))}만(지금 `{prot}`)")
        if migration_lint.WRAPPED_KEY_COLUMN.search(column) and (grade, prot) != ("비밀", "암호"):
            self.add(line, "S-SEC-10", f"{where}는 KEK로 감싼 행 키 — 등급 `비밀`, 보호 `암호`(지금 `{grade}`·`{prot}`)")
        if column == REST or name_exception or column.endswith(("_bidx", "_bidx_kid")):
            return
        name = snake(column)
        if SECRET_NAME.search(name) and grade != "비밀":
            self.add(line, "S-SEC-2", f"{where} 이름이 비밀값처럼 보임 — 등급 `비밀`(아니면 `이름 예외: 이유`)")
        elif PERSONAL_NAME.search(name) and RANK[grade] < RANK["개인"]:
            self.add(line, "S-SEC-2", f"{where} 이름이 개인정보처럼 보임 — 등급 `개인` 이상(아니면 `이름 예외: 이유`)")

    def read_sql(self, start: int, body: str) -> None:
        for st in sqltext.split(body).statements:
            m = re.match(rf"^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?({QNAME})\s*(\(.*)$", st.text, re.I | re.S)
            if not m:
                continue
            table = parse_qname(m.group(1))[1]
            inner, _ = paren_body(m.group(2), 0)
            columns: list[str] = []
            for element in split_top_level(inner):
                if re.match(r"^(INDEX|PROJECTION|CONSTRAINT|PRIMARY|UNIQUE|CHECK|FOREIGN|EXCLUDE|LIKE)\b", element, re.I):
                    continue
                col = re.match(rf"^({IDENT})\s", element)
                if col:
                    columns.append(col.group(1).strip('"'))
            self.sql_tables[table] = (start + st.line, columns)

    def check_sql_coverage(self) -> None:
        for table, (line, columns) in self.sql_tables.items():
            classified = self.classified.get(table)
            if classified is None:
                self.add(line, "S-SEC-1", f"`{table}`의 열 등급 표가 없음(`| 테이블 | 열 | 등급 | 보호 |`)")
                continue
            if REST in classified:
                continue
            missing = [c for c in columns if c not in classified]
            if missing:
                self.add(line, "S-SEC-1", f"`{table}` 열 등급이 빠짐: {', '.join(missing)}")

    def check_sections(self) -> None:
        for section in sections(self.lines):
            text = "\n".join(section.text)
            for table in section.tables:
                has_table = table in self.classified or table in self.sql_tables
                if not has_table:
                    continue
                if "보관" not in text and "보관" not in section.title:
                    self.add(section.line, "S-SEC-6", f"`{table}` 절에 보관 기한·파기 방법(`보관`)이 없음")
        # 테이블 제목인데 열 표도 SQL도 없는 절(문장으로만 적은 테이블)
        all_sections = sections(self.lines)
        for index, section in enumerate(all_sections):
            title = section.title
            following = all_sections[index + 1] if index + 1 < len(all_sections) else None
            if following is not None and following.level > section.level:
                continue  # 아래 절을 묶는 제목(DB 이름 등)
            if len(section.tables) == 1 and re.match(r"^(?:[\d.]+\s+)?`(?:(?:[A-Za-z_]|<[^>`]+>)(?:[A-Za-z0-9_.]|<[^>`]+>)*)`", title):
                table = section.tables[0]
                if table not in self.classified and table not in self.sql_tables:
                    self.add(section.line, "S-SEC-1", f"`{table}` 절에 열 표가 없음(문장으로만 적음)")


def check_text(rel: str, text: str) -> list[Problem]:
    """설계서 글 하나를 판정한다(시험이 직접 부름)."""
    return DocCheck(rel, text).run()


def design_docs(root: Path) -> list[Path]:
    """`crates/`·`docs/` 아래 `*data-model.md`. 빼는 폴더(target 등)는 아예 내려가지 않는다."""
    out: list[Path] = []
    for base in (root / "crates", root / "docs"):
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            out.extend(Path(dirpath) / name for name in filenames if name.endswith("data-model.md"))
    return sorted(out)


def service_docs(root: Path, service: str) -> list[Path]:
    """서비스 하나의 설계서: `crates/services/<서비스>/`와 `docs/spec/<서비스>/` 아래 `*data-model.md`."""
    return [p for p in design_docs(root) if p.relative_to(root).parts[:3] == ("crates", "services", service)
            or p.relative_to(root).parts[:3] == ("docs", "spec", service)]


def service_classification(root: Path, service: str) -> dict[str, dict[str, str]]:
    """서비스 설계서들의 테이블 → 열 → 등급."""
    classified: dict[str, dict[str, str]] = {}
    for doc in service_docs(root, service):
        check = DocCheck(doc.relative_to(root).as_posix(), doc.read_text(encoding="utf-8"))
        check.run()
        for table, columns in check.classified.items():
            classified.setdefault(table, {}).update(columns)
    return classified


def service_dirs(root: Path) -> list[tuple[Path, str]]:
    """PostgreSQL 이관 폴더와 그 서비스 이름(설계서를 찾는 이름. 키 DB 폴더도 그 서비스 설계서에 적음)."""
    out: list[tuple[Path, str]] = []
    for directory in migration_lint.migration_dirs(root):
        rel_dir = directory.relative_to(root)
        service = migration_lint.owning_service(rel_dir)
        if service and not any("clickhouse" in part for part in rel_dir.parts):
            out.append((directory, service))
    return out


def migration_coverage(root: Path) -> list[Problem]:
    """서비스 이관이 만드는 테이블의 열마다 그 서비스 설계서에 등급이 있는지(S-SEC-1). 설계서 표 형식만 보면 놓치는 것을 잡는다."""
    problems: list[Problem] = []
    for directory, service in service_dirs(root):
        classified = service_classification(root, service)
        for path in sorted(directory.glob("*.sql")):
            rel = path.relative_to(root).as_posix()
            schema = migration_lint.default_schema(directory.relative_to(root))
            for table, columns in migration_lint.created_tables(path.read_text(encoding="utf-8"), "postgres", schema).items():
                known = classified.get(table)
                if known is None:
                    problems.append(Problem(rel, 1, "S-SEC-1", f"이관이 만드는 `{table}`의 열 등급 표가 `{service}` 설계서에 없음"))
                    continue
                if REST in known:
                    continue
                missing = [c for c in columns if c not in known]
                if missing:
                    problems.append(Problem(rel, 1, "S-SEC-1", f"이관의 `{table}` 열이 설계서 등급 표에 없음: {', '.join(missing)}"))
    return problems


@dataclass
class ReaderAccess:
    """서비스 코드가 엔진 이관기에 넘기는 읽기 계정 설정(E-DB-12). 엔진 기본은 닫힘(9f027fa): 정하지 않은 표는 읽기 계정이 못 봄.
    연 표: `reader_all_tables()`(스키마 전체) 또는 `READER_TABLES`(`reader_table`). 감춘 표·열만 연 표는 그보다 앞섬."""

    hidden: set[str] = field(default_factory=set)
    columns: dict[str, list[str]] = field(default_factory=dict)
    tables: set[str] = field(default_factory=set)
    all_tables: bool = False
    recon_views: set[str] = field(default_factory=set)  # 대사 계정(`_recon`)이 읽는 보기(E-DB-15 `recon_view`)
    problems: list[Problem] = field(default_factory=list)


RECON_VIEWS = re.compile(r"\bconst\s+RECON_VIEWS\s*:[^=]*=\s*&\[(.*?)\]\s*;", re.S)
CREATED_VIEW = re.compile(rf"^CREATE\s+(?:MATERIALIZED\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?({QNAME})", re.I)
READER_TABLES = re.compile(r"\bconst\s+READER_TABLES\s*:[^=]*=\s*&\[(.*?)\]\s*;", re.S)
READER_HIDDEN = re.compile(r"\bconst\s+READER_HIDDEN\s*:[^=]*=\s*&\[(.*?)\]\s*;", re.S)
READER_COLUMNS = re.compile(r"\bconst\s+READER_COLUMNS\s*:[^=]*=\s*&\[(.*?)\]\s*;", re.S)
READER_COLUMN_ITEM = re.compile(r"\(\s*\"([^\"]+)\"\s*,\s*&\[(.*?)\]\s*,?\s*\)", re.S)  # rustfmt 끝 쉼표(`],\n)`)도
LITERAL = re.compile(r"\"([^\"]*)\"")


def passed_to(text: str, declaration: re.Match, const: str, call: str) -> bool:
    """상수를 실제로 엔진 호출에 넘기는지: 선언을 뺀 글에서 상수 이름을 쓴 자리 바로 뒤(400자 안)에 `.<call>(`이 있어야 한다
    (QA 795bf8c: 호출 글자만 따로 있어도 통과하던 것)."""
    rest = text[: declaration.start()] + text[declaration.end():]
    return re.search(rf"\b{const}\b[\s\S]{{0,400}}?\.{call}\(", rest) is not None


def reader_access(crate: Path, root: Path) -> ReaderAccess:
    """서비스 크레이트 `src/`의 `const READER_HIDDEN: &[&str]`·`const READER_COLUMNS: &[(&str, &[&str])]`를 읽는다(sql.md S-SEC-9).
    정한 모양으로만 적게 해야 검사가 코드와 같은 것을 본다: 상수를 두고 같은 파일에서 `reader_hidden`·`reader_columns`로 넘긴다."""
    access = ReaderAccess()
    src = crate / "src"
    if not src.is_dir():
        return access
    for path in sorted(src.rglob("*.rs")):
        rel = path.relative_to(root).as_posix()
        text = migration_lint.strip_rust_comments(path.read_text(encoding="utf-8"))
        hidden = READER_HIDDEN.search(text)
        # 넘기지 않은 상수는 엔진이 모르므로 감춘 것으로 세지 않는다.
        if hidden and passed_to(text, hidden, "READER_HIDDEN", "reader_hidden"):
            access.hidden.update(LITERAL.findall(hidden.group(1)))
        elif hidden:
            access.problems.append(Problem(rel, 1, "S-SEC-9", "`READER_HIDDEN`을 적었지만 이 파일에서 그 상수를 `reader_hidden`으로 넘기지 않음"))
        columns = READER_COLUMNS.search(text)
        if columns and passed_to(text, columns, "READER_COLUMNS", "reader_columns"):
            for table, listed in READER_COLUMN_ITEM.findall(columns.group(1)):
                access.columns[table] = LITERAL.findall(listed)
        elif columns:
            access.problems.append(Problem(rel, 1, "S-SEC-9", "`READER_COLUMNS`를 적었지만 이 파일에서 그 상수를 `reader_columns`로 넘기지 않음"))
        tables = READER_TABLES.search(text)
        if tables and passed_to(text, tables, "READER_TABLES", "reader_table"):
            access.tables.update(LITERAL.findall(tables.group(1)))
        elif tables:
            access.problems.append(Problem(rel, 1, "S-SEC-9", "`READER_TABLES`를 적었지만 이 파일에서 그 상수를 `reader_table`로 넘기지 않음"))
        recon = RECON_VIEWS.search(text)
        if recon and passed_to(text, recon, "RECON_VIEWS", "recon_view"):
            access.recon_views.update(LITERAL.findall(recon.group(1)))
        elif recon:
            access.problems.append(Problem(rel, 1, "S-SEC-9", "`RECON_VIEWS`를 적었지만 이 파일에서 그 상수를 `recon_view`로 넘기지 않음"))
        if ".recon_view(" in text and not recon:
            access.problems.append(Problem(rel, 1, "S-SEC-9", "`recon_view`에 넘기는 보기는 `const RECON_VIEWS`에 적음(검사가 읽는 자리)"))
        if re.search(r"\.reader_all_tables\(\s*\)", text):
            access.all_tables = True
        for call, found in (("reader_hidden", hidden), ("reader_columns", columns), ("reader_table", tables)):
            if f".{call}(" in text and not found:
                const = {"reader_hidden": "READER_HIDDEN", "reader_columns": "READER_COLUMNS", "reader_table": "READER_TABLES"}[call]
                access.problems.append(Problem(rel, 1, "S-SEC-9", f"`{call}`에 넘기는 표는 `const {const}`에 적음(검사가 읽는 자리)"))
    return access


def high_columns(classified: dict[str, dict[str, str]], table: str) -> list[str]:
    """등급이 `개인` 이상인 열(`(나머지)` 포함)."""
    return [c for c, g in classified.get(table, {}).items() if RANK.get(g, 0) >= RANK["개인"]]


def reader_coverage(root: Path) -> list[Problem]:
    """S-SEC-9: 등급 `개인` 이상 열이 있는 표를 읽기 계정(`<서비스>_ro`)에 표째 열지 않는다. 엔진 기본은 닫힘이라 열지 않은 표는
    괜찮고, `reader_all_tables()`·`READER_TABLES`로 열었으면 그 표는 감추거나(`READER_HIDDEN`) 그 열을 뺀 열만 연다(`READER_COLUMNS`)."""
    problems: list[Problem] = []
    for directory, service in service_dirs(root):
        classified = service_classification(root, service)
        access = reader_access(directory.parent, root)
        problems += access.problems
        created: dict[str, str] = {}
        views: set[str] = set()
        for path in sorted(directory.glob("*.sql")):
            text = path.read_text(encoding="utf-8")
            for table in migration_lint.created_tables(text, "postgres", service):
                created.setdefault(table, path.relative_to(root).as_posix())
            for st in sqltext.split(text).statements:
                view = CREATED_VIEW.match(st.text)
                if view:
                    views.add(parse_qname(view.group(1))[1])
        where = directory.parent.relative_to(root).as_posix()
        for view in sorted(access.recon_views - views):
            problems.append(Problem(where, 1, "S-SEC-9", f"`RECON_VIEWS`의 `{view}`를 이관이 보기(`CREATE VIEW`)로 만들지 않음(엔진 `grant_recon`도 거부)"))
        for table in sorted(access.hidden | set(access.columns) | access.tables):
            if table not in created:
                problems.append(Problem(where, 1, "S-SEC-9", f"읽기 계정 설정의 `{table}`을 이관이 만들지 않음(엔진 `grant`도 거부)"))
        for table, rel in sorted(created.items()):
            high = high_columns(classified, table)
            if not high or table in access.hidden:
                continue
            if table not in access.columns:
                if table in access.tables:
                    problems.append(Problem(rel, 1, "S-SEC-9", f"`READER_TABLES`가 `개인` 이상 열({', '.join(high)})이 있는 `{table}`을 표째 엶 — `READER_COLUMNS`로 그 열을 빼고 열기"))
                elif access.all_tables:
                    problems.append(Problem(rel, 1, "S-SEC-9", f"`reader_all_tables()`가 `{table}`의 `개인` 이상 열({', '.join(high)})까지 엶 — `READER_HIDDEN` 또는 `READER_COLUMNS`"))
                continue
            known = classified.get(table, {})
            for column in access.columns[table]:
                if column in high or (column not in known and REST in high):
                    problems.append(Problem(rel, 1, "S-SEC-9", f"`READER_COLUMNS`가 `{table}.{column}`(등급 `개인` 이상)을 읽기 계정에 엶"))
                elif column not in known:
                    problems.append(Problem(rel, 1, "S-SEC-9", f"`READER_COLUMNS`의 `{table}.{column}`이 설계서 등급 표에 없음"))
    return problems


ENGINE_CODE = (("crates", "engine"), ("crates", "apps", "mookko-runtime"))


def engine_reader_coverage(root: Path) -> list[Problem]:
    """S-SEC-9 엔진 몫(QA 795bf8c): 엔진 표 설계서(`docs/architecture/engine*data-model.md`, `crates/engine/**/data-model.md`)에서
    이름이 정해진 표(`<원장>`처럼 서비스가 이름을 정하는 표 말고)에 `개인` 이상 열이 있으면, 엔진 코드(`crates/engine/*`,
    `crates/apps/mookko-runtime`)의 `READER_HIDDEN`·`READER_COLUMNS`가 그 표를 읽기 계정에서 감춰야 한다."""
    docs = [p for p in design_docs(root)
            if p.relative_to(root).parts[:2] == ("crates", "engine")
            or (p.relative_to(root).parts[:2] == ("docs", "architecture") and p.name.startswith("engine"))]
    access = ReaderAccess()
    for parts in ENGINE_CODE:
        base = root.joinpath(*parts)
        crates = [base] if (base / "src").is_dir() else sorted(d for d in base.glob("*") if (d / "src").is_dir()) if base.is_dir() else []
        for crate in crates:
            found = reader_access(crate, root)
            access.hidden |= found.hidden
            access.columns.update(found.columns)
            # 엔진 시험(적합성)은 표를 직접 넘기므로 모양 지적은 서비스에만 한다.
    problems: list[Problem] = []
    for doc in docs:
        rel = doc.relative_to(root).as_posix()
        check = DocCheck(rel, doc.read_text(encoding="utf-8"))
        check.run()
        for table in sorted(check.classified):
            high = high_columns(check.classified, table)
            if "<" in table or not high or table in access.hidden:
                continue
            opened = [c for c in access.columns.get(table, []) if c in high]
            if table not in access.columns:
                problems.append(Problem(rel, 1, "S-SEC-9", f"엔진 표 `{table}`의 `개인` 이상 열({', '.join(high)})을 엔진 코드가 읽기 계정에서 감추지 않음 — `READER_HIDDEN`·`READER_COLUMNS`"))
            elif opened:
                problems.append(Problem(rel, 1, "S-SEC-9", f"엔진 `READER_COLUMNS`가 `{table}`의 `개인` 이상 열({', '.join(opened)})을 엶"))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="검사할 저장소 뿌리(시험용)")
    parser.add_argument("--pending", type=Path, default=pending.LIST, help="기한부 유예 목록(시험용)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    load_problems: list[str] = []
    waivers = pending.load(load_problems, args.pending)
    docs = design_docs(root)
    failing: list[Problem] = []
    waived_docs = 0
    for path in docs:
        rel = path.relative_to(root).as_posix()
        found = check_text(rel, path.read_text(encoding="utf-8"))
        item = pending.match(waivers, rel)
        if found and pending.is_waived(item):
            waived_docs += 1
            print(f"  유예({item.owner}, {item.until} 까지): {rel} — 고칠 것 {len(found)}건")
            for p in found:
                print(f"      {p}")
            continue
        if not found and item is not None:
            print(f"  알림: {rel}은 이제 통과합니다 — pending.json에서 지워도 됩니다")
        failing += found
    for problem in migration_coverage(root) + reader_coverage(root) + engine_reader_coverage(root):
        item = pending.match(waivers, problem.path, problem.rule)
        if pending.is_waived(item):
            print(f"  유예({item.owner}, {item.until} 까지): {problem}")
        else:
            failing.append(problem)
    if failing or load_problems:
        print(f"data class check failed ({len(failing) + len(load_problems)}):")
        for line in load_problems:
            print(f"  - {line}")
        for p in failing:
            print(f"  - {p}")
        return 1
    print(f"data class check passed ({len(docs)} design docs, 유예 {waived_docs})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

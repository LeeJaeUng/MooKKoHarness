"""SQL 글을 문장으로 나누는 작은 도구 (scripts/ci/db 검사들이 함께 씀).

완전한 SQL 파서가 아니다. 검사가 잘못 읽지 않도록 다음만 정확히 다룬다.
- `--` 줄 주석, `/* */` 묶음 주석(겹침 포함)은 지운다. 첫 문장 앞의 `-- mookko:<이름> <값>` 줄은 머리 지시로 모은다.
- 작은따옴표 문자열(`''` 이스케이프, `E'..'`의 `\\'`)은 `''`로 바꾼다(값 안의 낱말을 문장으로 읽지 않게).
- 달러 인용 본문(`$$ … $$`, `$tag$ … $tag$`, 함수 본문)은 `$$$$`로 바꾼다.
- 큰따옴표 이름은 그대로 둔다(검사가 찾아서 막음).
- 맨 바깥의 `;`에서 문장을 나누고, 공백은 하나로 줄인다.
근거: docs/policy/conventions/sql.md, docs/architecture/database.md §7.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DIRECTIVE = re.compile(r"^--\s*mookko:([a-z-]+)\s*(.*?)\s*$")
IDENT_CHAR = re.compile(r"[A-Za-z0-9_$]")
DOLLAR_TAG = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")


@dataclass(frozen=True)
class Statement:
    """문장 하나: 가린 글(`text`), 주석만 뺀 원문(`raw`, 문자열 값이 필요한 `SET` 등), 시작 줄(1부터)."""

    text: str
    raw: str
    line: int


@dataclass
class Script:
    """나눈 결과: 문장들, 머리 지시(이름 → (값, 줄)), 잘못 놓인 지시 줄."""

    statements: list[Statement] = field(default_factory=list)
    directives: dict[str, tuple[str, int]] = field(default_factory=dict)
    duplicate_directives: list[tuple[str, int]] = field(default_factory=list)
    late_directives: list[int] = field(default_factory=list)


def _skip_block_comment(sql: str, i: int) -> int:
    depth = 0
    n = len(sql)
    while i < n:
        if sql.startswith("/*", i):
            depth += 1
            i += 2
        elif sql.startswith("*/", i):
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return n


def _skip_string(sql: str, i: int, backslash: bool) -> int:
    """`i`는 여는 `'` 다음 글자. 닫는 `'` 다음 위치를 돌려준다."""
    n = len(sql)
    while i < n:
        ch = sql[i]
        if backslash and ch == "\\":
            i += 2
            continue
        if ch == "'":
            if i + 1 < n and sql[i + 1] == "'":
                i += 2
                continue
            return i + 1
        i += 1
    return n


def _skip_quoted_ident(sql: str, i: int) -> int:
    n = len(sql)
    while i < n:
        if sql[i] == '"':
            if i + 1 < n and sql[i + 1] == '"':
                i += 2
                continue
            return i + 1
        i += 1
    return n


def split(sql: str) -> Script:
    """SQL 글을 문장으로 나눈다."""
    script = Script()
    sql = sql.replace("\r\n", "\n")
    n = len(sql)
    i = 0
    line = 1
    buf: list[str] = []
    raw: list[str] = []
    start_line = 0

    def flush() -> None:
        nonlocal buf, raw, start_line
        text = " ".join("".join(buf).split())
        if text:
            script.statements.append(Statement(text=text, raw=" ".join("".join(raw).split()), line=start_line))
        buf = []
        raw = []
        start_line = 0

    def emit(piece: str, original: str | None = None) -> None:
        nonlocal start_line
        if start_line == 0 and piece.strip():
            start_line = line
        buf.append(piece)
        raw.append(piece if original is None else original)

    def space() -> None:
        buf.append(" ")
        raw.append(" ")

    while i < n:
        ch = sql[i]
        if ch == "\n":
            line += 1
            space()
            i += 1
        elif sql.startswith("--", i):
            end = sql.find("\n", i)
            end = n if end < 0 else end
            comment = sql[i:end]
            match = DIRECTIVE.match(comment)
            if match:
                if script.statements or start_line:
                    script.late_directives.append(line)
                elif match.group(1) in script.directives:
                    script.duplicate_directives.append((match.group(1), line))
                else:
                    script.directives[match.group(1)] = (match.group(2), line)
            space()
            i = end
        elif sql.startswith("/*", i):
            end = _skip_block_comment(sql, i)
            line += sql.count("\n", i, end)
            space()
            i = end
        elif ch == "'":
            backslash = i > 0 and sql[i - 1] in "eE" and (i < 2 or not IDENT_CHAR.match(sql[i - 2]))
            end = _skip_string(sql, i + 1, backslash)
            line += sql.count("\n", i, end)
            emit("''", sql[i:end])
            i = end
        elif ch == '"':
            end = _skip_quoted_ident(sql, i + 1)
            line += sql.count("\n", i, end)
            emit(sql[i:end])
            i = end
        elif ch == "$" and (i == 0 or not IDENT_CHAR.match(sql[i - 1])):
            match = DOLLAR_TAG.match(sql, i)
            if match:
                tag = match.group(0)
                close = sql.find(tag, match.end())
                end = n if close < 0 else close + len(tag)
                line += sql.count("\n", i, end)
                emit(" $$$$ ", sql[i:end])
                i = end
            else:
                emit(ch)
                i += 1
        elif ch == ";":
            flush()
            i += 1
        else:
            emit(ch)
            i += 1
    flush()
    return script


def split_top_level(text: str, sep: str = ",") -> list[str]:
    """괄호 밖의 `sep`에서 나눈다(문자열은 이미 가려져 있다고 본다)."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def paren_body(text: str, open_index: int) -> tuple[str, int]:
    """`text[open_index]`가 `(`일 때 짝이 맞는 `)`까지의 안쪽과 `)` 다음 위치."""
    depth = 0
    for j in range(open_index, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : j], j + 1
    return text[open_index + 1 :], len(text)


IDENT = r'(?:"(?:[^"]|"")+"|[A-Za-z_][A-Za-z0-9_$]*)'
QNAME = rf"{IDENT}(?:\s*\.\s*{IDENT})?"


def parse_qname(text: str) -> tuple[str | None, str]:
    """`schema.name` 또는 `name`을 (스키마, 이름)으로. 따옴표 없는 이름은 소문자로."""
    parts = [p.strip() for p in re.findall(IDENT, text)]

    def norm(p: str) -> str:
        return p[1:-1].replace('""', '"') if p.startswith('"') else p.lower()

    if len(parts) >= 2:
        return norm(parts[0]), norm(parts[1])
    return None, norm(parts[0]) if parts else ""

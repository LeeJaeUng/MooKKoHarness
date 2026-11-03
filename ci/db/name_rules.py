"""이름 종류별 CHECK 글 맞춤 검사 (docs/policy/conventions/sql.md S-NAME-2, qa-design XC-D5).

같은 종류의 이름(직원 ID·행위자·`*_by`·동작 이름·슬러그·영수증 키)은 서비스마다 DB 마지막 관문이 같아야 한다. 엔진 이름 규칙(C3)이
종류마다 SQL CHECK 글 한 벌을 내고, 그 글을 `name-checks.json`(SHA·출처)에 등록한다. 이 검사는 서비스 이관에서 그 종류의 열(이름이
`columns` 정규식에 맞음)마다 등록 글과 같은 CHECK가 그 폴더 이관 어딘가에 있는지 본다(새 넓히기에서 `NOT VALID`로 맞춰도 됨).
- 글은 엔진 `NameKind::sql_check(본보기 열)`의 출력 그대로(`CHECK (char_length("열") BETWEEN 1 AND N AND "열" ~ '^…$')`)이고,
  `sample_column`이 그 본보기 열 이름이다. 본보기 열 이름(따옴표 있든 없든)을 실제 열 이름으로 바꾸고, 공백·괄호·큰따옴표·`::text`·
  대소문자를 고른 뒤 같음으로 비교한다(서비스 이관은 이름에 따옴표를 쓰지 않음, S-TYPE-6).
- 등록 글이 바뀌지 않았는지 `sha256`(등록한 글 그대로)을 본다. 서비스 사이 공유 SQL 함수는 쓰지 않는다(S-BND-1).
- 등록부가 비어 있으면 아무것도 보지 않는다(엔진 C3 전). 이미 있는 열은 `pending.json` 유예로 둔다.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import migration_lint as ml
import sqltext

REGISTRY = Path(__file__).resolve().parent / "name-checks.json"
CHECK_OPEN = re.compile(r"\bCHECK\s*\(", re.I)


@dataclass(frozen=True)
class NameKind:
    kind: str
    columns: re.Pattern[str]
    check: str
    sample: str
    source: str

    def expected(self, column: str) -> str:
        return re.sub(rf'"?\b{re.escape(self.sample)}\b"?', column, self.check)


def normalized(text: str) -> str:
    flat = re.sub(r'[\s()"]', "", text.replace("::text", "")).lower()
    return flat[len("check"):] if flat.startswith("check") else flat


def load(path: Path = REGISTRY) -> tuple[list[NameKind], list[str]]:
    """등록부를 읽는다. 칸이 빠졌거나 SHA가 글과 다르면 문제로 돌려준다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    kinds: list[NameKind] = []
    problems: list[str] = []
    for item in data.get("kinds", []):
        missing = [k for k in ("kind", "columns", "check", "sample_column", "sha256", "source") if not item.get(k)]
        if missing:
            problems.append(f"name-checks.json: `{item.get('kind', '?')}` 칸 빠짐 {', '.join(missing)}")
            continue
        if not re.search(rf"\b{re.escape(item['sample_column'])}\b", item["check"]):
            problems.append(f"name-checks.json: `{item['kind']}` 글에 본보기 열 `{item['sample_column']}`이 없음")
            continue
        if hashlib.sha256(item["check"].encode("utf-8")).hexdigest() != item["sha256"]:
            problems.append(f"name-checks.json: `{item['kind']}` 글의 SHA가 다름 — 엔진 C3 출력을 그대로 다시 등록")
            continue
        kinds.append(NameKind(item["kind"], re.compile(item["columns"]), item["check"], item["sample_column"], item["source"]))
    return kinds, problems


def check_bodies(text: str) -> list[str]:
    out: list[str] = []
    for m in CHECK_OPEN.finditer(text):
        body, _ = sqltext.paren_body(text, m.end() - 1)
        out.append(body)
    return out


def lint_name_checks(root: Path, kinds: list[NameKind]) -> list[ml.Finding]:
    """서비스 이관 폴더마다: 종류 열마다 등록 글과 같은 CHECK가 있는가(S-NAME-2)."""
    findings: list[ml.Finding] = []
    if not kinds:
        return findings
    for directory in ml.migration_dirs(root):
        rel_dir = directory.relative_to(root)
        if any("clickhouse" in part for part in rel_dir.parts):
            continue
        schema = ml.default_schema(rel_dir)
        columns: list[tuple[str, str, str]] = []  # (파일, 표, 열)
        bodies: set[str] = set()
        for path in sorted(directory.glob("*.sql")):
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(root).as_posix()
            for table, cols, _ in ml.column_types(text, "postgres", schema):
                columns.append((rel, table, cols))
            for st in sqltext.split(text).statements:
                bodies.update(normalized(b) for b in check_bodies(st.raw))  # text는 글자 상수를 비워 둠 — 정규식까지 맞추려면 원문
        for rel, table, column in columns:
            for kind in kinds:
                if not kind.columns.fullmatch(column):
                    continue
                want = normalized(kind.expected(column))
                # NULL을 받는 열은 `열 IS NULL OR (등록 글)`로 감싸 건다(그 모양만 같은 글로 봄).
                if want not in bodies and normalized(f"{column} IS NULL OR ") + want not in bodies:
                    findings.append(ml.Finding(rel, 1, "S-NAME-2", f"`{table}.{column}`({kind.kind})의 CHECK가 등록 글과 다름 — `{kind.expected(column)}`(출처 {kind.source})"))
    return findings

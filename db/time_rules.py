"""시각·ID 출처 검사 (docs/policy/conventions/sql.md S-TIME-1, S-TYPE-1 시간대).

- S-TIME-1: 서비스 SQL의 시각은 엔진 Clock이 넘긴 `$now`(트랜잭션마다 하나), 새 ID는 앱 `TimeOrderedId`로 바인딩한다. DB 시계·ID 함수
  (`now()`·`clock_timestamp()`·`current_timestamp`·`uuidv7()`·`gen_random_uuid()` 등)는 트리거 함수 안(늦은 값 막기 같은 하한)과 엔진이
  만든 DDL 기본값에만 쓴다. 앱 서버와 DB 시계가 어긋나면 기한 비교가 어긋나고, 엔진 Clock으로 멈춘 시험이 SQL 쪽 시각에 먹지 않는다
  (qa-design XC-D3).
  - 서비스·실행 파일 `src/`의 Rust 문자열(SQL 주석은 지움), 서비스 이관의 함수 밖 문장(`DEFAULT now()` 등). 시험 코드(`tests/`)는 보지 않음.
  - 엔진 생성 고정 파일(`engine-generated.json`)과 `mookko-runtime`은 엔진 몫이라 보지 않음.
- S-TYPE-1(경고): 시각을 날짜·달로 자르거나 글자로 바꿀 때(`date_trunc(` 두 인자·`::date`·`to_char(`) 같은 글 안에 `AT TIME ZONE`이 없으면
  세션 시간대에 기댄다고 경고한다. 인자 형식을 글로 모르므로 실패가 아니라 경고.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import migration_lint as ml
import sqltext

DB_CLOCK = re.compile(
    r"\b(now|clock_timestamp|statement_timestamp|transaction_timestamp|timeofday|uuidv7|uuidv4|gen_random_uuid)\s*\(\s*\)"
    r"|\b(current_timestamp|localtimestamp|current_date|current_time|localtime)\b",
    re.I,
)
CREATE_FUNCTION = re.compile(r"^CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\b", re.I)
SKIP_CODE = ("crates/apps/mookko-runtime/",)
TRUNC_TWO_ARGS = re.compile(r"\bdate_trunc\s*\(\s*'[^']*'\s*,\s*[^,()]+(?:\([^()]*\))?\s*\)", re.I)
TO_DATE_TEXT = re.compile(r"::\s*date\b|\bto_char\s*\(", re.I)
AT_TIME_ZONE = re.compile(r"\bAT\s+TIME\s+ZONE\b", re.I)


def clock_message(match: re.Match[str]) -> str:
    name = match.group(0).strip()
    return f"서비스 SQL의 DB 시계·ID 함수 `{name}` 금지 — 시각은 엔진 Clock의 `$now`, 새 ID는 앱 `TimeOrderedId`로 바인딩(트리거 하한·엔진 DDL 기본값만 예외)"


def service_code(root: Path) -> list[Path]:
    out: list[Path] = []
    for base in (root / "crates" / "services", root / "crates" / "apps"):
        out += [p for p in ml.walk(base, lambda name: name.endswith(".rs")) if "src" in p.relative_to(base).parts and "tests" not in p.relative_to(base).parts]
    return [p for p in out if not p.relative_to(root).as_posix().startswith(SKIP_CODE)]


def engine_fixed(registry_path: Path) -> set[str]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    return {item["path"] for item in registry.get("files", []) if item.get("path")}


def lint_time_sources(root: Path, registry_path: Path) -> list[ml.Finding]:
    """S-TIME-1: 서비스 코드 SQL 문자열과 서비스 이관(함수 본문 밖)의 DB 시계·ID 함수."""
    findings: list[ml.Finding] = []
    for path in service_code(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        for start, body in ml.rust_strings(text):
            flat = " ".join(ml.strip_sql_comments(body).split())
            for match in DB_CLOCK.finditer(flat):
                findings.append(ml.Finding(rel, text.count("\n", 0, start) + 1, "S-TIME-1", clock_message(match)))
    fixed = engine_fixed(registry_path)
    for directory in ml.migration_dirs(root):
        if any("clickhouse" in part for part in directory.relative_to(root).parts):
            continue
        for path in sorted(directory.glob("*.sql")):
            rel = path.relative_to(root).as_posix()
            if rel in fixed:
                continue
            # 키 DB 키 표의 `created_at DEFAULT now()`는 §9.8이 정한 모양이고 엔진 `RowKeyStore`가 그 기본값에 기댐(엔진이 `$now`를 넘기면 걷음).
            key_dir = ml.is_key_dir(directory.relative_to(root))
            for st in sqltext.split(path.read_text(encoding="utf-8")).statements:
                if CREATE_FUNCTION.match(st.text):
                    continue  # 트리거 함수 안의 하한(늦은 값 막기)은 DB 시계가 맞음
                if key_dir and re.match(r"^CREATE\s+TABLE\b", st.text, re.I):
                    continue
                for match in DB_CLOCK.finditer(st.text):
                    findings.append(ml.Finding(rel, st.line, "S-TIME-1", clock_message(match)))
    return findings


def timezone_warnings(root: Path) -> list[str]:
    """S-TYPE-1 경고: 시각을 자르거나 글자로 바꾸는 글에 `AT TIME ZONE`이 없음."""
    warnings: list[str] = []

    def check(rel: str, line: int, flat: str) -> None:
        if (TRUNC_TWO_ARGS.search(flat) or TO_DATE_TEXT.search(flat)) and not AT_TIME_ZONE.search(flat):
            warnings.append(f"{rel}:{line}: S-TYPE-1 시각을 날짜·달로 자르거나 글자로 바꾸는데 `AT TIME ZONE 'UTC'`가 없음(세션 시간대에 기댐)")

    for path in service_code(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        for start, body in ml.rust_strings(text):
            check(rel, text.count("\n", 0, start) + 1, " ".join(ml.strip_sql_comments(body).split()))
    for directory in ml.migration_dirs(root):
        if any("clickhouse" in part for part in directory.relative_to(root).parts):
            continue
        for path in sorted(directory.glob("*.sql")):
            for st in sqltext.split(path.read_text(encoding="utf-8")).statements:
                check(path.relative_to(root).as_posix(), st.line, st.text)
    return warnings

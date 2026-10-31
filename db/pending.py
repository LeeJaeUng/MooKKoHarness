"""기한부 유예 목록 (scripts/ci/db/pending.json).

DB 규약이 생기기 전에 들어온 파일(이관·설계서)은 담당이 고칠 때까지 기한을 두고 경고로만 알린다.
기한이 지나면 그 파일의 판정이 다시 실패가 된다. 목록에 없는 새 파일은 처음부터 실패.
항목: path(파일 또는 폴더, 저장소 기준), owner, until(YYYY-MM-DD), reason, 고를 수 있는 rules(규칙 ID 목록 — 있으면 그 규칙 판정만 유예하고,
규칙을 넘기지 않는 검사(migration_lint)에는 효력이 없음). 근거: docs/policy/conventions/sql.md.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path

LIST = Path(__file__).resolve().parent / "pending.json"


@dataclass(frozen=True)
class Pending:
    """유예 항목 하나."""

    path: str
    owner: str
    until: datetime.date
    reason: str
    rules: tuple[str, ...] = ()


def load(problems: list[str], path: Path = LIST) -> list[Pending]:
    """목록을 읽는다. 칸이 빠지면 problems에 적는다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[Pending] = []
    for item in data.get("pending", []):
        missing = [k for k in ("path", "owner", "until", "reason") if not item.get(k)]
        if missing:
            problems.append(f"pending.json: {item} 에 {missing} 칸이 없음")
            continue
        out.append(Pending(item["path"], item["owner"], datetime.date.fromisoformat(item["until"]), item["reason"], tuple(item.get("rules", ()))))
    return out


def match(items: list[Pending], rel: str, rule: str | None = None) -> Pending | None:
    """rel(저장소 기준 경로)을 덮는 항목. 규칙을 고른 항목은 그 규칙(rule)의 판정에만 맞는다."""
    for item in items:
        if item.rules and rule not in item.rules:
            continue
        if rel == item.path or rel.startswith(item.path.rstrip("/") + "/"):
            return item
    return None


def is_waived(item: Pending | None, today: datetime.date | None = None) -> bool:
    """기한 안의 유예인가."""
    return item is not None and (today or datetime.date.today()) <= item.until

"""관문 waived 예외 등록부 검사(docs/policy/waivers.json, gates.md › waived).

waived는 근거 문서와 만료일이 있는 등록부 항목이 있어야 한다. 이 검사는 항목마다 칸이 다 있는지, paths와 adr이 가리키는
파일이 저장소에 있는지, 만료일이 지나지 않았고 오늘부터 MAX_DAYS 안인지(끝없는 예외 막기), id가 겹치지 않는지를 본다. 하나라도 어기면 실패한다.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]  # 인자를 주면 표본 폴더를 검사
REGISTRY = ROOT / "docs" / "policy" / "waivers.json"
MAX_DAYS = 180  # 예외는 길어야 반년. 더 필요하면 다시 승인받아 날짜를 고친다.
FIELDS = ("id", "paths", "rule", "reason", "adr", "condition", "expires", "approvedBy")


def check(data: dict, today: datetime.date) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for item in data.get("waivers", []):
        name = item.get("id") or "(id 없음)"
        missing = [k for k in FIELDS if not item.get(k)]
        if missing:
            problems.append(f"waivers.json: {name}: 빠진 칸 {missing}")
            continue
        if name in seen:
            problems.append(f"waivers.json: {name}: id가 겹침")
        seen.add(name)
        try:
            expires = datetime.date.fromisoformat(item["expires"])
        except ValueError:
            problems.append(f"waivers.json: {name}: expires가 YYYY-MM-DD가 아님: {item['expires']}")
            continue
        if expires < today:
            problems.append(f"waivers.json: {name}: {item['expires']}에 만료됨({item['condition']})")
        elif (expires - today).days > MAX_DAYS:
            problems.append(f"waivers.json: {name}: expires {item['expires']}가 오늘부터 {MAX_DAYS}일을 넘음")
        for rel in item["paths"]:
            if not (ROOT / rel).exists():
                problems.append(f"waivers.json: {name}: 없는 경로 {rel}")
        adr_path = item["adr"].split()[0].rstrip(",")
        if not (ROOT / adr_path).exists():
            problems.append(f"waivers.json: {name}: adr 근거 문서가 없음 {adr_path}")
    return problems


def main() -> int:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    problems = check(data, datetime.date.today())
    if problems:
        print("waiver check failed:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"waiver check passed ({len(data.get('waivers', []))} waivers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

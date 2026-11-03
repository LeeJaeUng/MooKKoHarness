"""취약점·패치 지연 기록부 검사 (SEC-04, 하네스 policy/conventions/security.md SC-VULN-1·3, 근거 제품
docs/architecture/host-security.md §1.1, 보안 담당 요청 2026-11-04).

벤더 패치가 기한(KEV·실제 공격 48시간, 치명 7일)을 못 맞추면 제품 docs/policy/vuln-register.json에 항목을 연다. 파일이 없으면
열린 항목이 없는 것으로 보고 통과한다. 있으면 항목마다 본다(waivers.json 검사와 같은 방식).
- 칸: id, affects(목록), exposure, mitigations(목록, 기다리기만 하는 항목은 받지 않음), opened, reviewBy, expires, owner
- 날짜는 YYYY-MM-DD, expires는 opened부터 MAX_DAYS 안(30일 넘으면 사용자 결정 → 새 항목으로 다시 엶)
- id가 겹치지 않음
- 닫지 않은 항목(closed 없음)의 expires가 지났으면 실패(사용자 결정이 필요), reviewBy가 지났으면 경고(매일 다시 봄)
- closed는 YYYY-MM-DD이고 opened 뒤. 닫은 항목은 지우지 않고 남긴다(기한은 보지 않음)
실패하면 `docs/policy/vuln-register.json:1: 이유`를 한 줄씩 내고 1, 경고는 `경고:`로 시작하는 줄.

사용: python3 -X utf8 ci/check-vuln-register.py [저장소 루트]
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

REL = "docs/policy/vuln-register.json"
MAX_DAYS = 30  # 완화로 버티는 최대 기간(host-security §1.1, SC-VULN-1)
FIELDS = ("id", "affects", "exposure", "mitigations", "opened", "reviewBy", "expires", "owner")


def day(value: object) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def check(data: dict, today: datetime.date) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(data.get("entries", [])):
        name = item.get("id") or f"entries[{i}]"
        missing = [k for k in FIELDS if not item.get(k)]
        if missing:
            problems.append(f"{REL}:1: {name}: 빠진 칸 {missing}")
            continue
        if name in seen:
            problems.append(f"{REL}:1: {name}: id가 겹칩니다")
        seen.add(name)
        if not isinstance(item["affects"], list) or not isinstance(item["mitigations"], list):
            problems.append(f"{REL}:1: {name}: affects·mitigations는 목록이어야 합니다")
        dates = {k: day(item[k]) for k in ("opened", "reviewBy", "expires")}
        bad = [k for k, v in dates.items() if v is None]
        if bad:
            problems.append(f"{REL}:1: {name}: {bad}가 YYYY-MM-DD가 아닙니다")
            continue
        if (dates["expires"] - dates["opened"]).days > MAX_DAYS:
            problems.append(f"{REL}:1: {name}: expires {item['expires']}가 opened부터 {MAX_DAYS}일을 넘습니다(넘으면 사용자 결정)")
        if "closed" in item:
            closed = day(item["closed"])
            if closed is None or closed < dates["opened"]:
                problems.append(f"{REL}:1: {name}: closed {item['closed']}는 opened 뒤의 YYYY-MM-DD여야 합니다")
            continue
        if dates["expires"] < today:
            problems.append(f"{REL}:1: {name}: {item['expires']}에 기한이 지났습니다(고친 판을 올려 닫거나 사용자 결정)")
        elif dates["reviewBy"] < today:
            warnings.append(f"{REL}:1: {name}: reviewBy {item['reviewBy']}가 지났습니다(매일 다시 보고 날짜를 올리세요)")
    return problems, warnings


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    path = root / REL
    if not path.exists():
        print("vuln register check passed (no register)")
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"{REL}:1: JSON을 읽지 못했습니다: {e}")
        print("vuln register check failed (1 problems)")
        return 1
    problems, warnings = check(data, datetime.date.today())
    for line in problems:
        print(line)
    for line in warnings:
        print(f"경고: {line}")
    entries = data.get("entries", [])
    open_count = sum(1 for e in entries if isinstance(e, dict) and "closed" not in e)
    if problems:
        print(f"vuln register check failed ({len(problems)} problems)")
        return 1
    print(f"vuln register check passed ({len(entries)} entries, {open_count} open, {len(warnings)} warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

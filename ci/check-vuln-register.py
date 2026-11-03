"""취약점·패치 지연 기록부 검사 (SEC-04, 하네스 policy/conventions/security.md SC-VULN-1~3, 근거 제품
docs/architecture/host-security.md §1·§1.1, 보안 담당 요청 2026-11-04, mookko-rust-qa 11-04 지적 반영).

벤더 패치가 기한(KEV·실제 공격 48시간, 치명 7일)을 못 맞추면 제품 docs/policy/vuln-register.json에 항목을 연다. 파일이 없으면
열린 항목이 없는 것으로 보고 통과한다. 있으면 `entries` 목록이 있어야 하고 항목마다 본다(waivers.json 검사와 같은 방식).
- 칸: id(항목 번호, 겹치지 않음), cve, severity(kev|critical), published(공개·KEV 등재일), affects(목록), exposure,
  mitigations(목록, 항목마다 {kind, what}), opened, reviewBy, expires, owner. 날짜는 YYYY-MM-DD
- 기한 절반 전에 열기: 그 cve를 처음 연 항목의 opened가 published부터 severity 기한의 절반(kev 1일, critical 3일) 안
- 완화(SC-VULN-2): kind가 MITIGATION_KINDS(노출 끊기·격리·감지 강화·다른 이미지) 중 하나 이상. 기다리기만 하는 항목은 받지 않음
- 30일 상한: 같은 cve의 가장 이른 opened부터 셈. 이 항목의 expires가 그 날부터 MAX_DAYS를 넘으면 userDecision(사용자 결정 근거)이
  있어야 함 — id만 바꿔 다시 열어 상한을 비켜 가지 못하게
- reviewBy는 opened~expires 안
- 닫지 않은 항목(closed 없음)의 expires가 지났으면 실패(사용자 결정이 필요), reviewBy가 지났으면 경고(매일 다시 봄)
- closed는 opened 뒤의 YYYY-MM-DD이고 fixedIn(고친 판·근거)이 있어야 함. 닫은 항목은 지우지 않고 남긴다(기한은 보지 않음)
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
MAX_DAYS = 30  # 완화로 버티는 최대 기간(host-security §1.1, SC-VULN-1). 넘으면 사용자 결정
FIELDS = ("id", "cve", "severity", "published", "affects", "exposure", "mitigations", "opened", "reviewBy", "expires", "owner")
OPEN_WITHIN_DAYS = {"kev": 1, "critical": 3}  # 패치 기한(KEV·실제 공격 48시간, 치명 7일)의 절반 안에 연다
MITIGATION_KINDS = {"cut-exposure", "isolate", "detect", "alternate-image"}  # host-security §1.1 완화 순서


def day(value: object) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def check(data: object, today: datetime.date) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return [f"{REL}:1: `entries` 목록이 없습니다"], warnings
    seen: set[str] = set()
    first_opened: dict[str, datetime.date] = {}
    for item in entries:
        if isinstance(item, dict) and isinstance(item.get("cve"), str) and day(item.get("opened")):
            opened = day(item["opened"])
            first_opened[item["cve"]] = min(first_opened.get(item["cve"], opened), opened)
    for i, item in enumerate(entries):
        if not isinstance(item, dict):
            problems.append(f"{REL}:1: entries[{i}]는 객체여야 합니다")
            continue
        name = str(item.get("id") or f"entries[{i}]")
        missing = [k for k in FIELDS if not item.get(k)]
        if missing:
            problems.append(f"{REL}:1: {name}: 빠진 칸 {missing}")
            continue
        if name in seen:
            problems.append(f"{REL}:1: {name}: id가 겹칩니다")
        seen.add(name)
        if not isinstance(item["affects"], list) or not isinstance(item["mitigations"], list):
            problems.append(f"{REL}:1: {name}: affects·mitigations는 목록이어야 합니다")
            continue
        kinds = {m.get("kind") for m in item["mitigations"] if isinstance(m, dict) and m.get("what")}
        if not kinds & MITIGATION_KINDS:
            problems.append(f"{REL}:1: {name}: 완화에 kind {sorted(MITIGATION_KINDS)} 중 하나 이상과 what이 있어야 합니다"
                            f"(기다리기만 하는 항목은 받지 않음, SC-VULN-2)")
        if item["severity"] not in OPEN_WITHIN_DAYS:
            problems.append(f"{REL}:1: {name}: severity는 {sorted(OPEN_WITHIN_DAYS)} 중 하나")
        dates = {k: day(item[k]) for k in ("published", "opened", "reviewBy", "expires")}
        bad = [k for k, v in dates.items() if v is None]
        if bad:
            problems.append(f"{REL}:1: {name}: {bad}가 YYYY-MM-DD가 아닙니다")
            continue
        within = OPEN_WITHIN_DAYS.get(item["severity"])
        start = first_opened.get(item["cve"], dates["opened"])
        if within is not None and dates["opened"] == start and (dates["opened"] - dates["published"]).days > within:
            problems.append(f"{REL}:1: {name}: published {item['published']}부터 {within}일(기한의 절반) 안에 열어야 합니다(opened {item['opened']})")
        if (dates["expires"] - start).days > MAX_DAYS and not item.get("userDecision"):
            problems.append(f"{REL}:1: {name}: {item['cve']}를 처음 연 {start.isoformat()}부터 {MAX_DAYS}일을 넘습니다 — "
                            f"userDecision(사용자 결정 근거)이 있어야 합니다")
        if not dates["opened"] <= dates["reviewBy"] <= dates["expires"]:
            problems.append(f"{REL}:1: {name}: reviewBy {item['reviewBy']}는 opened~expires 안이어야 합니다")
        if "closed" in item:
            closed = day(item["closed"])
            if closed is None or closed < dates["opened"]:
                problems.append(f"{REL}:1: {name}: closed {item['closed']}는 opened 뒤의 YYYY-MM-DD여야 합니다")
            if not item.get("fixedIn"):
                problems.append(f"{REL}:1: {name}: 닫은 항목에 fixedIn(고친 판·근거)이 없습니다")
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
    if problems:
        print(f"vuln register check failed ({len(problems)} problems)")
        return 1
    entries = data["entries"]
    open_count = sum(1 for e in entries if "closed" not in e)
    print(f"vuln register check passed ({len(entries)} entries, {open_count} open, {len(warnings)} warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""취약점·패치 지연 기록부 검사 (SEC-04, 하네스 policy/conventions/security.md SC-REG-1·SC-VULN-1~3, 근거 제품
docs/architecture/host-security.md §1·§1.1, 보안 담당 기준 2026-11-04 ee18cf1, mookko-rust-qa 11-04 지적 반영).

벤더 패치가 기한(KEV·실제 공격 48시간, 치명 7일)을 못 맞추면 제품 docs/policy/vuln-register.json에 항목을 연다.
- 파일은 늘 있어야 한다(빈 목록이어도, SC-REG-1). `entries`는 목록, 원소는 객체
- 칸: id(`CVE-YYYY-N…`·`GHSA-xxxx-xxxx-xxxx`, 한 id에 항목은 평생 하나), affects(목록, `pool:`·`image:`·`host:` 접두어), exposure,
  mitigations(목록, 항목마다 {kind, action}), opened, reviewBy, expires, owner. 날짜는 YYYY-MM-DD
- 완화(④): kind는 MITIGATION_KINDS만, action은 빈 글이 아님. 열린 항목에는 detect 밖의 kind가 하나 이상(기다리기·감지만은 안 됨)
- 기한(⑤): expires ≤ opened + MAX_DAYS. 넘기려면 userDecision {date, ref}(사용자 결정 기록 위치)가 있고 expires ≤ date + MAX_DAYS
- reviewBy는 opened~expires 안. 닫지 않은 항목(closed 없음)의 expires가 지났으면 실패, reviewBy가 지났으면 경고(매일 다시 봄)
- closed는 opened 뒤의 YYYY-MM-DD이고 fixedIn(고친 판·근거)이 있어야 함. 닫은 항목도 지우지 않는다
- 기준 브랜치와 대조(⑤): MOOKKO_REGISTER_BASE(없으면 foundation/engine)의 기록부에 있던 id가 사라지거나 opened가 바뀌면 실패.
  검사 폴더가 git 최상위가 아니면(표본) 대조하지 않고, git·기준 판을 읽지 못하면 "건너뜀"을 내고 MOOKKO_REQUIRE_GIT_HISTORY=1이면 실패
실패하면 `docs/policy/vuln-register.json:1: 이유`를 한 줄씩 내고 1, 경고는 `경고:`로 시작하는 줄.

사용: python3 -X utf8 ci/check-vuln-register.py [저장소 루트]
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REL = "docs/policy/vuln-register.json"
MAX_DAYS = 30  # 완화로 버티는 최대 기간(host-security §1.1, SC-VULN-1). 넘으면 사용자 결정
FIELDS = ("id", "affects", "exposure", "mitigations", "opened", "reviewBy", "expires", "owner")
ID = re.compile(r"^(CVE-\d{4}-\d{4,}|GHSA(-[23456789cfghjmpqrvwx]{4}){3})$")
AFFECTS = re.compile(r"^(pool|image|host):\S")
MITIGATION_KINDS = {"block-exposure", "isolate", "disable-feature", "detect", "alt-image"}  # SC-VULN-1 ④
DEFAULT_BASE = "foundation/engine"
NOT_TOP = "검사 폴더가 git 최상위가 아님(표본)"


def day(value: object) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def check_entry(item: dict, name: str, today: datetime.date, problems: list[str], warnings: list[str]) -> None:
    missing = [k for k in FIELDS if not item.get(k)]
    if missing:
        problems.append(f"{REL}:1: {name}: 빠진 칸 {missing}")
        return
    if not ID.match(name):
        problems.append(f"{REL}:1: {name}: id는 CVE-YYYY-N… 또는 GHSA-xxxx-xxxx-xxxx 꼴만")
    if not isinstance(item["affects"], list) or not all(isinstance(a, str) and AFFECTS.match(a) for a in item["affects"]):
        problems.append(f"{REL}:1: {name}: affects는 `pool:`·`image:`·`host:` 접두어 글의 목록")
    mitigations = item["mitigations"] if isinstance(item["mitigations"], list) else []
    bad = [m for m in mitigations if not (isinstance(m, dict) and m.get("kind") in MITIGATION_KINDS
                                          and isinstance(m.get("action"), str) and m["action"].strip())]
    if not mitigations or bad:
        problems.append(f"{REL}:1: {name}: mitigations는 {{kind, action}} 목록, kind는 {sorted(MITIGATION_KINDS)}, action은 빈 글이 아님")
    elif "closed" not in item and not {m["kind"] for m in mitigations} - {"detect"}:
        problems.append(f"{REL}:1: {name}: 열린 항목에는 detect 밖의 완화(노출 끊기·격리·기능 끄기·다른 이미지)가 하나 이상 있어야 합니다(SC-VULN-2)")
    dates = {k: day(item[k]) for k in ("opened", "reviewBy", "expires")}
    wrong = [k for k, v in dates.items() if v is None]
    if wrong:
        problems.append(f"{REL}:1: {name}: {wrong}가 YYYY-MM-DD가 아닙니다")
        return
    decision = item.get("userDecision")
    if (dates["expires"] - dates["opened"]).days > MAX_DAYS:
        decided = day(decision.get("date")) if isinstance(decision, dict) and decision.get("ref") else None
        if decided is None:
            problems.append(f"{REL}:1: {name}: expires가 opened부터 {MAX_DAYS}일을 넘습니다 — userDecision {{date, ref}}가 있어야 합니다")
        elif (dates["expires"] - decided).days > MAX_DAYS:
            problems.append(f"{REL}:1: {name}: expires는 userDecision.date {decision['date']}부터 {MAX_DAYS}일 안이어야 합니다")
    if not dates["opened"] <= dates["reviewBy"] <= dates["expires"]:
        problems.append(f"{REL}:1: {name}: reviewBy {item['reviewBy']}는 opened~expires 안이어야 합니다")
    if "closed" in item:
        closed = day(item["closed"])
        if closed is None or closed < dates["opened"]:
            problems.append(f"{REL}:1: {name}: closed {item['closed']}는 opened 뒤의 YYYY-MM-DD여야 합니다")
        if not item.get("fixedIn"):
            problems.append(f"{REL}:1: {name}: 닫은 항목에 fixedIn(고친 판·근거)이 없습니다")
        return
    if dates["expires"] < today:
        problems.append(f"{REL}:1: {name}: {item['expires']}에 기한이 지났습니다(고친 판을 올려 닫거나 사용자 결정)")
    elif dates["reviewBy"] < today:
        warnings.append(f"{REL}:1: {name}: reviewBy {item['reviewBy']}가 지났습니다(매일 다시 보고 날짜를 올리세요)")


def check(data: object, today: datetime.date) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return [f"{REL}:1: `entries` 목록이 없습니다"], warnings
    seen: set[str] = set()
    for i, item in enumerate(entries):
        if not isinstance(item, dict):
            problems.append(f"{REL}:1: entries[{i}]는 객체여야 합니다")
            continue
        name = str(item.get("id") or f"entries[{i}]")
        if name in seen:
            problems.append(f"{REL}:1: {name}: id가 겹칩니다(한 id에 항목은 평생 하나)")
        seen.add(name)
        check_entry(item, name, today, problems, warnings)
    return problems, warnings


def git(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")
    return result.stdout if result.returncode == 0 else None


def base_entries(root: Path) -> tuple[dict[str, dict] | None, str]:
    """기준 브랜치의 기록부 항목(id → 항목). (None, 이유)면 대조하지 못함, ({}, "")이면 기준에 기록부가 없음."""
    top = git(root, "rev-parse", "--show-toplevel")
    if top is None:
        return None, "git을 읽지 못함"
    if Path(top.strip()).resolve() != root:
        return None, NOT_TOP
    ref = os.environ.get("MOOKKO_REGISTER_BASE") or DEFAULT_BASE
    if git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is None:
        return None, f"기준 판 {ref}를 읽지 못함"
    text = git(root, "show", f"{ref}:{REL}")
    if text is None:
        return {}, ""
    try:
        data = json.loads(text)
    except ValueError:
        return {}, ""
    entries = data.get("entries") if isinstance(data, dict) else None
    return {str(e["id"]): e for e in entries or [] if isinstance(e, dict) and e.get("id")}, ""


def compare(base: dict[str, dict], data: dict) -> list[str]:
    now = {str(e.get("id")): e for e in data.get("entries", []) if isinstance(e, dict)}
    problems = []
    for name, old in sorted(base.items()):
        if name not in now:
            problems.append(f"{REL}:1: {name}: 기준 판에 있던 항목이 사라졌습니다(닫은 항목도 지우지 않음, id를 바꾸지 않음)")
        elif now[name].get("opened") != old.get("opened"):
            problems.append(f"{REL}:1: {name}: opened가 기준 판 {old.get('opened')}에서 바뀌었습니다(기한을 늘리려면 userDecision)")
    return problems


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    path = root / REL
    if not path.exists():
        print(f"{REL}:1: 기록부가 없습니다(빈 목록이어도 늘 있어야 함, SC-REG-1)")
        print("vuln register check failed (1 problems)")
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"{REL}:1: JSON을 읽지 못했습니다: {e}")
        print("vuln register check failed (1 problems)")
        return 1
    problems, warnings = check(data, datetime.date.today())
    base, why = base_entries(root)
    if base is None:
        if os.environ.get("MOOKKO_REQUIRE_GIT_HISTORY") == "1" and why != NOT_TOP:
            problems.append(f"{REL}:1: 기준 판과 대조하지 못했습니다({why})")
        else:
            print(f"기준 판 대조 건너뜀(통과 아님): {why}")
    elif isinstance(data, dict):
        problems += compare(base, data)
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

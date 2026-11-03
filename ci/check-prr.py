"""출시 준비 검토(PRR) 문서 검사 (PRR-01 자동 근거, QAManager 요청 2026-11-03; 근거 docs/policy/gates.md PRR-01,
틀 docs/spec/prr-template.md).

docs/policy/prr.json의 서비스마다 docs/spec/<서비스>/prr.md를 본다.
- 파일이 없으면 한 건.
- "## 항목" 표에 틀의 아홉 항목(SLO·SLI, 경보, runbook, 당번, 용량, 의존 장애, 되돌리기, 비상 경로, 백업·복구)이 모두 있고,
  내용 칸이 비었거나 `-`·`TODO`뿐이면 항목마다 한 건("미정: 사유"는 됨).
- "## 경보와 runbook" 표에 경보가 하나도 없으면 한 건, 경보마다 runbook 칸이 저장소 안 문서 링크(`[이름](경로)`, 그 파일이
  있어야 함)가 아니면 한 건.
prr.json의 enforce가 false인 동안(QA 관문 1차 경고 단계, 출시 관문 L4 전까지) `경고:`로 내고 0, true면 `파일:줄: 이유`로 1.

사용: python3 -X utf8 scripts/ci/check-prr.py [저장소 루트]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ITEMS = ["SLO·SLI", "경보", "runbook", "당번", "용량", "의존 장애", "되돌리기", "비상 경로", "백업·복구"]
EMPTY = {"", "-", "—", "todo", "TODO", "tbd", "TBD"}
LINK = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")


def table_after(lines: list[str], heading: str) -> list[tuple[int, list[str]]]:
    """heading 아래 첫 표의 본문 행(머리줄·구분줄 뺌)."""
    rows: list[tuple[int, list[str]]] = []
    try:
        i = next(k for k, l in enumerate(lines) if l.strip() == heading)
    except StopIteration:
        return rows
    seen_header = False
    for k in range(i + 1, len(lines)):
        line = lines[k].strip()
        if line.startswith("## "):
            break
        if not line.startswith("|"):
            if rows or seen_header:
                if line:
                    break
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not seen_header:
            seen_header = True
            continue
        if set(line) <= set("|-: "):
            continue
        rows.append((k + 1, cells))
    return rows


def check(root: Path, service: str, problems: list[str]) -> None:
    rel = f"docs/spec/{service}/prr.md"
    path = root / rel
    if not path.exists():
        problems.append(f"{rel}:1: {service}의 출시 준비 검토 문서가 없습니다(docs/spec/prr-template.md를 복사해 채우세요)")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    items = {cells[0]: (no, cells[1] if len(cells) > 1 else "") for no, cells in table_after(lines, "## 항목")}
    for item in ITEMS:
        if item not in items:
            problems.append(f"{rel}:1: 항목 '{item}' 줄이 없습니다")
        elif items[item][1] in EMPTY:
            problems.append(f"{rel}:{items[item][0]}: 항목 '{item}'이 비었습니다(정하지 못했으면 '미정: 사유·언제')")
    alerts = table_after(lines, "## 경보와 runbook")
    if not alerts:
        problems.append(f"{rel}:1: '경보와 runbook' 표에 경보가 없습니다")
    for no, cells in alerts:
        name, runbook = cells[0], (cells[1] if len(cells) > 1 else "")
        m = LINK.search(runbook)
        if not m:
            problems.append(f"{rel}:{no}: 경보 '{name}'에 runbook 링크가 없습니다")
        elif not m.group(1).startswith(("http://", "https://")) and not (path.parent / m.group(1).split("#")[0]).resolve().exists():
            problems.append(f"{rel}:{no}: 경보 '{name}'의 runbook {m.group(1)}이 저장소에 없습니다")


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    try:
        policy = json.loads((root / "docs" / "policy" / "prr.json").read_text(encoding="utf-8"))
        enforce, services = policy["enforce"], policy["services"]
    except (OSError, ValueError, KeyError) as e:
        print(f"docs/policy/prr.json:1: 읽지 못했습니다: {e}")
        return 1
    problems: list[str] = []
    for service in services:
        check(root, service, problems)
    for p in problems:
        print(p if enforce else f"경고: {p}")
    mode = "enforce" if enforce else "warn only"
    if problems and enforce:
        print(f"prr check failed ({len(problems)} problems)")
        return 1
    print(f"prr check passed ({len(services)} services, {len(problems)} warnings, {mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

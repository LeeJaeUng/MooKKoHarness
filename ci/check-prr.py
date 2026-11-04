"""출시 준비 검토(PRR) 문서 검사 (PRR-01 자동 근거, QAManager 요청 2026-11-03; 근거 docs/policy/gates.md PRR-01,
틀 docs/spec/prr-template.md, qa-services 11-04 T1~T4 반영).

docs/policy/prr.json의 서비스마다 docs/spec/<서비스>/prr.md를 본다. 표는 머리줄의 열 이름으로 읽는다(열 순서는 상관없음).
- 파일이 없으면 한 건.
- "## 항목" 표: 틀의 아홉 항목(SLO·SLI, 경보, runbook, 당번, 용량, 의존 장애, 되돌리기, 비상 경로, 백업·복구)이 모두 있고,
  "내용" 칸이 비었거나 `-`·`TODO`뿐이면 한 건("미정: 사유"는 됨). 정한 칸은 PRR-01 하위 요구의 낱말이 있어야 함(T1):
  SLO·SLI → SLI·SLO·측정·오류 예산, 당번 → 대상·순번·단계·사후 검토, 백업·복구 → RPO·RTO·복구 훈련.
- "## 경보와 runbook" 표(T2): 열 경보·SLO·소진율 창·증상/원인·호출/티켓·runbook. 경보가 하나도 없으면 한 건, 경보마다 빈 칸,
  증상/원인은 `증상`·`원인`, 호출/티켓은 `호출`·`티켓` 중 하나, runbook은 저장소 안 문서 링크(`[이름](경로)`, 그 파일이 있어야 함).
- "## 사고 대응 훈련" 표(SEC-03 SC-IR-2, incident-response §8, T3): 열 훈련·날짜·걸린 시간·§5.1 목표·기록, 줄 탁상 훈련·기술 훈련.
- "## 정기 훈련·시험" 표(T4): 열 훈련·시험·날짜·기록, 줄 비상 경로 훈련·복구 훈련·되돌리기 시험(분기마다 했는지).
  두 훈련 표는 날짜 YYYY-MM-DD, 기록은 저장소 안 문서 링크, 나머지 칸은 비지 않음.
prr.json의 enforce가 false인 동안(QA 관문 1차 경고 단계, 출시 관문 L4 전까지) `경고:`로 내고 0, true면 `파일:줄: 이유`로 1.

사용: python3 -X utf8 ci/check-prr.py [저장소 루트]
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ITEMS = ["SLO·SLI", "경보", "runbook", "당번", "용량", "의존 장애", "되돌리기", "비상 경로", "백업·복구"]
ITEM_WORDS = {  # PRR-01 하위 요구(gates.md PRR-01 표): 정한 칸에 이 낱말이 다 있어야 함(qa-services T1)
    "SLO·SLI": ["SLI", "SLO", "측정", "오류 예산"],
    "당번": ["대상", "순번", "단계", "사후 검토"],
    "백업·복구": ["RPO", "RTO", "복구 훈련"],
}
ALERT_COLUMNS = ["경보", "SLO", "소진율 창", "증상/원인", "호출/티켓", "runbook"]  # SRE 워크북 5장(qa-services T2)
ALERT_CHOICES = {"증상/원인": {"증상", "원인"}, "호출/티켓": {"호출", "티켓"}}
DRILLS = ("## 사고 대응 훈련", ["훈련", "날짜", "걸린 시간", "§5.1 목표", "기록"], ["탁상 훈련", "기술 훈련"])  # incident-response §8
ROUTINE = ("## 정기 훈련·시험", ["훈련·시험", "날짜", "기록"], ["비상 경로 훈련", "복구 훈련", "되돌리기 시험"])  # qa-services T4
EMPTY = {"", "-", "—", "todo", "TODO", "tbd", "TBD"}
LINK = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def table(lines: list[str], heading: str) -> tuple[list[str], list[tuple[int, dict[str, str]]]] | None:
    """heading 아래 첫 표: (머리줄 열 이름, 본문 행마다 (줄 번호, 열 이름 → 칸)). 제목이 없으면 None."""
    try:
        i = next(k for k, l in enumerate(lines) if l.strip() == heading)
    except StopIteration:
        return None
    header: list[str] = []
    rows: list[tuple[int, dict[str, str]]] = []
    for k in range(i + 1, len(lines)):
        line = lines[k].strip()
        if line.startswith("## "):
            break
        if not line.startswith("|"):
            if (rows or header) and line:
                break
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not header:
            header = cells
            continue
        if set(line) <= set("|-: "):
            continue
        rows.append((k + 1, {name: (cells[n] if n < len(cells) else "") for n, name in enumerate(header)}))
    return header, rows


def linked(path: Path, cell: str) -> bool:
    m = LINK.search(cell)
    if not m:
        return False
    target = m.group(1)
    return target.startswith(("http://", "https://")) or (path.parent / target.split("#")[0]).resolve().exists()


def check_columns(rel: str, heading: str, header: list[str], want: list[str], problems: list[str]) -> bool:
    missing = [c for c in want if c not in header]
    if missing:
        problems.append(f"{rel}:1: '{heading[3:]}' 표에 열 {missing}이 없습니다(docs/spec/prr-template.md와 같게)")
    return not missing


def check_dated(rel: str, path: Path, lines: list[str], spec: tuple[str, list[str], list[str]], problems: list[str]) -> None:
    heading, columns, names = spec
    found = table(lines, heading)
    if found is None:
        problems.append(f"{rel}:1: '{heading[3:]}' 표가 없습니다(docs/spec/prr-template.md)")
        return
    header, rows = found
    if not check_columns(rel, heading, header, columns, problems):
        return
    by_name = {cells[columns[0]]: (no, cells) for no, cells in rows}
    for name in names:
        if name not in by_name:
            problems.append(f"{rel}:1: '{heading[3:]}'의 '{name}' 줄이 없습니다")
            continue
        no, cells = by_name[name]
        if not DATE.match(cells["날짜"]):
            problems.append(f"{rel}:{no}: '{name}'의 날짜가 YYYY-MM-DD가 아닙니다(아직 안 했으면 출시 관문에서 fail)")
        if not linked(path, cells["기록"]):
            problems.append(f"{rel}:{no}: '{name}'의 기록이 저장소 안 문서 링크가 아닙니다")
        blank = [c for c in columns[1:] if c not in ("날짜", "기록") and cells[c] in EMPTY]
        if blank:
            problems.append(f"{rel}:{no}: '{name}'의 {blank} 칸이 비었습니다")


def check(root: Path, service: str, problems: list[str]) -> None:
    rel = f"docs/spec/{service}/prr.md"
    path = root / rel
    if not path.exists():
        problems.append(f"{rel}:1: {service}의 출시 준비 검토 문서가 없습니다(docs/spec/prr-template.md를 복사해 채우세요)")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    found = table(lines, "## 항목")
    items = {cells.get("항목", ""): (no, cells.get("내용", "")) for no, cells in (found[1] if found else [])}
    for item in ITEMS:
        if item not in items:
            problems.append(f"{rel}:1: 항목 '{item}' 줄이 없습니다")
            continue
        no, content = items[item]
        if content in EMPTY:
            problems.append(f"{rel}:{no}: 항목 '{item}'이 비었습니다(정하지 못했으면 '미정: 사유·언제')")
        elif not content.startswith("미정") and item in ITEM_WORDS:
            missing = [w for w in ITEM_WORDS[item] if w not in content]
            if missing:
                problems.append(f"{rel}:{no}: 항목 '{item}'에 {missing}이 없습니다(PRR-01 하위 요구)")
    found = table(lines, "## 경보와 runbook")
    if found is None or not found[1]:
        problems.append(f"{rel}:1: '경보와 runbook' 표에 경보가 없습니다")
    elif check_columns(rel, "## 경보와 runbook", found[0], ALERT_COLUMNS, problems):
        for no, cells in found[1]:
            name = cells["경보"]
            blank = [c for c in ALERT_COLUMNS[1:-1] if cells[c] in EMPTY]
            if blank:
                problems.append(f"{rel}:{no}: 경보 '{name}'의 {blank} 칸이 비었습니다")
            for column, choices in ALERT_CHOICES.items():
                if cells[column] not in EMPTY and cells[column] not in choices:
                    problems.append(f"{rel}:{no}: 경보 '{name}'의 {column}는 {sorted(choices)} 중 하나")
            if not LINK.search(cells["runbook"]):
                problems.append(f"{rel}:{no}: 경보 '{name}'에 runbook 링크가 없습니다")
            elif not linked(path, cells["runbook"]):
                problems.append(f"{rel}:{no}: 경보 '{name}'의 runbook {LINK.search(cells['runbook']).group(1)}이 저장소에 없습니다")
    check_dated(rel, path, lines, DRILLS, problems)
    check_dated(rel, path, lines, ROUTINE, problems)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
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

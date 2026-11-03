"""설계 결정 표의 "표준 출처" 칸 검사 (docs/architecture/principles.md › 결정 표, PM 사용자 대행 2026-11-03,
사용자 "대기업에서 하는건 이유가 있는거야 최대한 대기업 서비스에 거의 맞게 우리는 제작이 되어야지 서비스가 가능해").

docs/architecture/·docs/spec/ 아래 *.md에서 결정 표를 찾는다. 결정 표는 머리줄 첫 칸이 "번호"이고, 어느 칸이든
"결정"이 들어 있는 표다.
- 머리줄에 "표준 출처" 칸이 없으면 그 표에 한 건.
- 칸이 있는데 행의 값이 비어 있거나 "-"이면 그 행에 한 건. 표준을 따르지 않으면 "해당 없음(사유)"이나
  "표준과 다름(사유·출처, PM 확인)"이라고 적는다(비어 있지만 않으면 통과).
docs/policy/design-sources.json의 enforce가 false이면 `경고:`로 시작하는 줄만 내고 0으로 끝난다(처음에는 경고만,
PM 지시). true이면 `파일:줄: 이유`를 내고 1로 끝난다. 설정 파일이 없거나 틀리면 실패한다.

사용: python3 -X utf8 scripts/ci/check-design-sources.py [저장소 루트]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

COLUMN = "표준 출처"
EMPTY = {"", "-", "—"}


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_separator(line: str) -> bool:
    return set(line.strip()) <= set("|-: ") and "-" in line


def tables(text: str):
    """(머리줄 번호, 머리 칸, [(줄 번호, 칸)])."""
    lines = text.splitlines()
    i = 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and is_separator(lines[i + 1]):
            head = cells(lines[i])
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append((j + 1, cells(lines[j])))
                j += 1
            yield i + 1, head, rows
            i = j
        else:
            i += 1


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    policy = root / "docs" / "policy" / "design-sources.json"
    try:
        enforce = json.loads(policy.read_text(encoding="utf-8"))["enforce"]
        if not isinstance(enforce, bool):
            raise ValueError("enforce는 true·false여야 합니다")
    except (OSError, ValueError, KeyError) as e:
        print(f"docs/policy/design-sources.json:1: 읽지 못했습니다: {e}")
        return 1
    problems: list[str] = []
    found = 0
    for base in (root / "docs" / "architecture", root / "docs" / "spec"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            rel = path.relative_to(root).as_posix()
            for head_no, head, rows in tables(path.read_text(encoding="utf-8")):
                if not head or head[0] != "번호" or not any("결정" in h for h in head):
                    continue
                found += 1
                if COLUMN not in head:
                    problems.append(f"{rel}:{head_no}: 결정 표에 '{COLUMN}' 칸이 없습니다")
                    continue
                col = head.index(COLUMN)
                for no, row in rows:
                    value = row[col] if col < len(row) else ""
                    if value in EMPTY:
                        problems.append(f"{rel}:{no}: {row[0]}의 '{COLUMN}'이 비었습니다(대용량 회사 표준 출처, 또는 다른 이유)")
    for p in problems:
        print(p if enforce else f"경고: {p}")
    if problems and enforce:
        print(f"design source check failed ({len(problems)} problems)")
        return 1
    mode = "enforce" if enforce else "warn only"
    print(f"design source check passed ({found} decision tables, {len(problems)} warnings, {mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

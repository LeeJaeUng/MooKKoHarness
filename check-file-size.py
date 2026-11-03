"""Rust 파일 길이 검사 (rust.md R-MOD-3 "파일 하나 600줄을 넘기면 나눈다", qa-engine 2026-11-03 지적: 자동 검사 없음).

crates/ 아래 src/의 *.rs마다, 맨 앞(열 0)의 첫 `#[cfg(test)]` 앞까지 줄 수를 센다(파일 안 시험 모듈은 빼고 셈).
tests/·benches/·examples/는 보지 않는다. 600줄을 넘으면 실패한다. 다만 docs/policy/waivers.json에 rule이 "R-MOD-3"으로
시작하고 paths에 그 파일이 든 항목이 있으면 넘어간다(기한·칸은 check-waivers.py가 검사). 예외가 있는데 600줄 이하가 되면
예외를 지우라고 실패한다(낡은 예외를 남기지 않음).
실패하면 `파일:줄: 이유`를 한 줄씩 내고 1로 끝난다.

사용: python3 -X utf8 scripts/ci/check-file-size.py [저장소 루트]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LIMIT = 600
SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist", "tests", "benches", "examples"}


def counted_lines(text: str) -> int:
    count = 0
    for line in text.splitlines():
        if line.startswith("#[cfg(test)]"):
            break
        count += 1
    return count


def waived_paths(root: Path) -> set[str]:
    path = root / "docs" / "policy" / "waivers.json"
    if not path.exists():
        return set()
    waivers = json.loads(path.read_text(encoding="utf-8")).get("waivers", [])
    return {p for w in waivers if str(w.get("rule", "")).startswith("R-MOD-3") for p in w.get("paths", [])}


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    waived = waived_paths(root)
    problems: list[str] = []
    scanned = 0
    for path in sorted((root / "crates").rglob("*.rs")):
        rel = path.relative_to(root)
        if "src" not in rel.parts or any(p in SKIP_DIRS for p in rel.parts):
            continue
        scanned += 1
        n = counted_lines(path.read_text(encoding="utf-8"))
        key = rel.as_posix()
        if n > LIMIT and key not in waived:
            problems.append(f"{key}:{LIMIT + 1}: 시험 모듈을 빼고 {n}줄입니다. {LIMIT}줄 이하로 나누세요(R-MOD-3)")
        elif n <= LIMIT and key in waived:
            problems.append(f"docs/policy/waivers.json:1: {key}는 {n}줄이라 R-MOD-3 예외가 더는 필요 없습니다. 예외를 지우세요")
    for p in problems:
        print(p)
    if problems:
        print(f"file size check failed ({len(problems)} problems)")
        return 1
    print(f"file size check passed ({scanned} files, {len(waived)} waived)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

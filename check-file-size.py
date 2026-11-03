"""Rust 파일 길이 검사 (rust.md R-MOD-3 "파일 하나 600줄을 넘기면 나눈다", qa-engine 2026-11-03 지적: 자동 검사 없음).

crates/ 아래 src/의 *.rs마다, `#[cfg(test)]`이 붙은 항목(시험 모듈 등)만 빼고 나머지 줄을 모두 센다(시험 모듈 뒤 코드도 셈).
tests/·benches/·examples/는 보지 않는다. 600줄을 넘으면 실패한다. 다만 docs/policy/waivers.json에 rule이 "R-MOD-3"으로
시작하고 paths에 그 파일이 든 항목이 있으면 넘어간다(기한·칸은 check-waivers.py가 검사). 예외가 있는데 600줄 이하가 되면
예외를 지우라고 실패한다(낡은 예외를 남기지 않음).
실패하면 `파일:줄: 이유`를 한 줄씩 내고 1로 끝난다.

사용: python3 -X utf8 scripts/ci/check-file-size.py [저장소 루트]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LIMIT = 600
SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist"}
# crate 바로 아래의 시험·벤치·예제 폴더만 뺀다. src/ 안의 `tests` 같은 모듈 폴더는 센다(QA 8f8cf0f 낮음).
CRATE_SIDE_DIRS = {"tests", "benches", "examples"}
TEST_MOD = re.compile(r"^\s*mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;")


def in_src(rel: Path) -> bool:
    """crates/<무리>/<crate>/src/… 이고 src 앞에 tests·benches·examples가 없는지."""
    parts = rel.parts
    if "src" not in parts:
        return False
    return not any(p in CRATE_SIDE_DIRS for p in parts[: parts.index("src")])


def test_module_files(path: Path, text: str) -> set[Path]:
    """`#[cfg(test)]` 다음 줄의 `mod 이름;`이 가리키는 파일(이름.rs, 이름/ 아래 전부). 시험 전용이라 세지 않는다(QA 8f8cf0f 낮음)."""
    lines = text.splitlines()
    base = path.parent if path.name in ("lib.rs", "main.rs", "mod.rs") else path.with_suffix("")
    found: set[Path] = set()
    for i, line in enumerate(lines[:-1]):
        if line.strip() == "#[cfg(test)]":
            m = TEST_MOD.match(lines[i + 1])
            if m:
                found.add(base / f"{m.group(1)}.rs")
                found.update((base / m.group(1)).rglob("*.rs"))
    return found


def counted_lines(text: str) -> int:
    """`#[cfg(test)]`이 붙은 항목(모듈·함수·use 등) 하나만 빼고 나머지 줄을 모두 센다. 처음엔 첫 `#[cfg(test)]`에서
    세기를 멈춰, 시험 모듈 뒤에 둔 코드를 세지 않는 구멍이 있었다(PM 11-03)."""
    lines = text.splitlines()
    count = 0
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("#[cfg(test)]"):
            # 붙은 항목의 끝까지 건너뜀: 중괄호가 열리면 닫힐 때까지, 아니면 `;`로 끝나는 줄까지.
            depth = 0
            opened = False
            j = i + 1 if lines[i].strip() == "#[cfg(test)]" else i
            while j < len(lines):
                code = lines[j].split("//", 1)[0]
                depth += code.count("{") - code.count("}")
                opened = opened or "{" in code
                if (opened and depth <= 0) or (not opened and code.rstrip().endswith(";")):
                    break
                j += 1
            i = j + 1
            continue
        count += 1
        i += 1
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
    files = [
        p for p in sorted((root / "crates").rglob("*.rs"))
        if in_src(p.relative_to(root)) and not any(part in SKIP_DIRS for part in p.relative_to(root).parts)
    ]
    texts = {p: p.read_text(encoding="utf-8") for p in files}
    test_only: set[Path] = set()
    for p, text in texts.items():
        test_only |= test_module_files(p, text)
    for key in sorted(waived):
        if not (root / key).is_file():
            problems.append(f"docs/policy/waivers.json:1: R-MOD-3 예외의 {key}가 없습니다(지웠거나 이름이 바뀜). 예외를 고치세요")
    for path in files:
        rel = path.relative_to(root)
        if path in test_only:
            continue
        scanned += 1
        n = counted_lines(texts[path])
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

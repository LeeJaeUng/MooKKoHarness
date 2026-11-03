"""규칙 끄기 검사 (docs/policy/conventions/README.md › 예외, rust.md §9, frontend.md §9).

워커가 lint를 주석으로 꺼서 규약을 피해 가지 못하게 한다.
- Rust: `#[allow(`, `#![allow(`, `#[expect(`, `#![expect(`, `cfg_attr(..., allow|expect(` 금지.
  예외는 시험 파일(`tests/` 아래) 머리의 `#![allow(clippy::unwrap_used, clippy::expect_used)]` 한 가지.
- TypeScript·JavaScript(web/): `eslint-disable`, `@ts-ignore`, `@ts-expect-error`, `@ts-nocheck` 금지.
- 그 밖은 docs/policy/lint-exceptions.json에 path·text·reason·expires로 등록된 줄만 허용, 만료되면 실패.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]  # 인자를 주면 표본 폴더를 검사
REGISTRY = ROOT / "docs" / "policy" / "lint-exceptions.json"
SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist"}

RUST_ESCAPE = re.compile(r"#!?\[\s*(allow|expect)\s*\(|cfg_attr\s*\([^)]*\b(allow|expect)\s*\(")
TS_ESCAPE = re.compile(r"eslint-disable|@ts-ignore|@ts-expect-error|@ts-nocheck")
TEST_HEADER = "#![allow(clippy::unwrap_used, clippy::expect_used)]"
TS_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}


def files(base: Path, suffixes: set[str]):
    if not base.exists():
        return
    for path in base.rglob("*"):
        rel = path.relative_to(ROOT)
        if path.is_file() and path.suffix in suffixes and not any(p in SKIP_DIRS for p in rel.parts):
            yield path, rel


def load_registry(problems: list[str]) -> dict[tuple[str, str], dict]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    today = datetime.date.today()
    allowed: dict[tuple[str, str], dict] = {}
    for item in data.get("exceptions", []):
        missing = [k for k in ("path", "text", "reason", "expires", "approvedBy") if not item.get(k)]
        if missing:
            problems.append(f"lint-exceptions.json: entry {item} is missing {missing}")
            continue
        if datetime.date.fromisoformat(item["expires"]) < today:
            problems.append(f"lint-exceptions.json: {item['path']} `{item['text']}` expired on {item['expires']}")
            continue
        allowed[(item["path"], item["text"].strip())] = item
    return allowed


def main() -> int:
    problems: list[str] = []
    allowed = load_registry(problems)
    scanned = 0
    targets = [(files(ROOT / "crates", {".rs"}), RUST_ESCAPE), (files(ROOT / "web", TS_SUFFIXES), TS_ESCAPE)]
    for walker, pattern in targets:
        for path, rel in walker:
            scanned += 1
            in_tests = "tests" in rel.parts
            for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                text = line.strip()
                if not pattern.search(text):
                    continue
                if in_tests and text == TEST_HEADER:
                    continue
                if (rel.as_posix(), text) in allowed:
                    continue
                problems.append(f"{rel.as_posix()}:{no}: rule escape `{text}` is not registered")
    if problems:
        print("lint escape check failed (fix the code, or register in docs/policy/lint-exceptions.json):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"lint escape check passed ({scanned} files, {len(allowed)} registered exceptions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""시험 안 실제 sleep·실제 시각 검사 (TEST-01, mookko-rust-qa 2026-11-03 QA 관문 초안 판정 "추가 5"; 근거
docs/policy/gates.md TEST-01, docs/coordination/harness-backlog.md).

실제 시간에 기대는 시험은 느리고 흔들립니다. 시험은 주입한 시계(엔진 C2 FixedClock)와 멈춘 tokio 시간을 씁니다.
- SLEEP: `std::thread::sleep(`, `tokio::time::sleep(`(`time::sleep(`). 다만 그 파일이 `start_paused`나 `time::pause()`로
  tokio 시간을 멈추면 tokio sleep은 됨(실제로 기다리지 않음).
- NOW: `SystemTime::now(`, `OffsetDateTime::now_utc(`, `Timestamp::now(`, `Utc::now(`. 시험은 FixedClock을 주입.
보는 곳: crates/·acceptance/의 시험 코드 — crate 바로 아래 tests/ 폴더와 src/ 안의 `#[cfg(test)]` 항목.
문자열·주석 안은 보지 않는다(check-hardcoded-values.py와 같은 지우기).

지금 있는 것은 docs/policy/test-time.json baseline(파일마다 규칙별 개수, 기한 expires)에 두고 옮긴다.
- enforce false(처음): 기준을 넘는 것을 `경고:`로 내고 0.
- enforce true: 기준보다 많아지면 그 줄을 `파일:줄: 이유`로 내고 실패, 줄면 기준을 낮추라고 실패, 기한이 지나면 실패.
`--list`는 걸린 줄을 모두, `--write-baseline`은 지금 개수로 기준을 다시 쓴다(통합 담당만).

사용: python3 -X utf8 scripts/ci/check-test-time.py [저장소 루트] [--list] [--write-baseline]
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("hardcoded", HERE / "check-hardcoded-values.py")
assert _spec and _spec.loader
hardcoded = importlib.util.module_from_spec(_spec)
sys.modules["hardcoded"] = hardcoded
_spec.loader.exec_module(hardcoded)

SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist", "fixtures"}
SLEEP = re.compile(r"\bthread::sleep\s*\(|\btime::sleep\s*\(|(?<![\w:])sleep\s*\(\s*Duration")
TOKIO_SLEEP = re.compile(r"\btokio::time::sleep\s*\(|(?<!thread::)\btime::sleep\s*\(")
PAUSED = re.compile(r"start_paused\s*=\s*true|\btime::pause\s*\(")
NOW = re.compile(r"\b(SystemTime::now|OffsetDateTime::now_utc|Timestamp::now|Utc::now)\s*\(")
RULE_TEXT = {
    "SLEEP": "시험이 실제로 잠듭니다. 주입한 시계나 멈춘 tokio 시간(start_paused)을 쓰고 조건을 기다리세요",
    "NOW": "시험이 실제 시각을 읽습니다. 엔진 C2 FixedClock을 주입하세요",
}


def test_lines(path: Path, rel: Path):
    """시험 코드 줄: tests/ 아래면 전부, src/ 안이면 `#[cfg(test)]` 항목만. (줄 번호, 원래 줄, 지운 줄)."""
    text = path.read_text(encoding="utf-8")
    masked = hardcoded.mask(text).splitlines()
    raw = text.splitlines()
    parts = rel.parts
    if "tests" in parts and ("src" not in parts or parts.index("tests") < parts.index("src")):
        for i, line in enumerate(masked):
            yield i + 1, raw[i], line
        return
    product = {no for no, _, _ in hardcoded.code_lines(text)}
    for i, line in enumerate(masked):
        if i + 1 not in product:
            yield i + 1, raw[i], line


def scan(root: Path) -> list[tuple[str, str, int, str]]:
    hits: list[tuple[str, str, int, str]] = []
    for base in ("crates", "acceptance"):
        if not (root / base).exists():
            continue
        for path in sorted((root / base).rglob("*.rs")):
            rel = path.relative_to(root)
            if any(p in SKIP_DIRS for p in rel.parts):
                continue
            paused = bool(PAUSED.search(path.read_text(encoding="utf-8")))
            for no, raw, code in test_lines(path, rel):
                if SLEEP.search(code) and not (paused and TOKIO_SLEEP.search(code) and "thread::sleep" not in code):
                    hits.append((rel.as_posix(), "SLEEP", no, raw.strip()))
                if NOW.search(code):
                    hits.append((rel.as_posix(), "NOW", no, raw.strip()))
    return hits


def main() -> int:
    return hardcoded.ratchet_main("test time", "docs/policy/test-time.json", scan, RULE_TEXT)


if __name__ == "__main__":
    sys.exit(main())

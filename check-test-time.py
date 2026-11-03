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
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    root = Path(args[0]).resolve() if args else HERE.parents[1]
    policy_path = root / "docs" / "policy" / "test-time.json"
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        enforce, baseline, expires = policy["enforce"], policy["baseline"], policy["expires"]
        expired = datetime.date.fromisoformat(expires) < datetime.date.today()
    except (OSError, ValueError, KeyError) as e:
        print(f"docs/policy/test-time.json:1: 읽지 못했습니다: {e}")
        return 1
    hits = scan(root)
    found = hardcoded.counts(hits)
    if "--write-baseline" in flags:
        policy["baseline"] = found
        policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"baseline을 다시 썼습니다({len(found)} 파일, {len(hits)} 건)")
        return 0
    if "--list" in flags:
        for rel, rule, no, text in hits:
            print(f"{rel}:{no}: [{rule}] {text}")
    problems: list[str] = []
    for rel in sorted(set(found) | set(baseline)):
        for rule in sorted(set(found.get(rel, {})) | set(baseline.get(rel, {}))):
            now, allowed = found.get(rel, {}).get(rule, 0), baseline.get(rel, {}).get(rule, 0)
            if now > allowed:
                problems.extend(f"{r}:{n}: {RULE_TEXT[k]} ({k}, 기준 {allowed}건, 지금 {now}건): {t[:120]}"
                                for r, k, n, t in hits if r == rel and k == rule)
            elif now < allowed:
                problems.append(f"docs/policy/test-time.json:1: {rel} {rule}가 {allowed}건에서 {now}건으로 줄었습니다. 기준을 낮추세요")
            elif now and expired:
                problems.append(f"{rel}:1: {rule} {now}건이 기한 {expires}을 넘겨 남아 있습니다. 옮기세요")
    for p in problems:
        print(p if enforce else f"경고: {p}")
    summary = ", ".join(f"{k} {sum(1 for h in hits if h[1] == k)}" for k in RULE_TEXT)
    if problems and enforce:
        print(f"test time check failed ({len(problems)} problems; {summary})")
        return 1
    mode = "enforce" if enforce else "warn only"
    print(f"test time check passed ({summary}; {len(problems)} warnings, baseline {len(baseline)} files, {mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

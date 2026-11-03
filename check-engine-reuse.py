"""엔진 공용 기능을 서비스가 다시 만들지 못하게 하는 검사 (PM 사용자 대행 2026-11-03, 사용자 "공용으로 쓸수있는 기능은
엔진에 작업을 넘겨서 엔진에서 작업해야해"; 근거 docs/coordination/engine-priority.md › 공용화 C1~C4).

crates/services/·crates/apps/ 아래 src/의 *.rs(주석 줄은 뺌, tests/·benches/·examples/는 보지 않음)에서 아래 모양을 찾는다.
- C1 최근 MFA: 서비스가 정한 기한·시계 오차 상수(`const RECENT_MFA…`, `const MFA_…`)
- C2 시계·시각: `trait Clock`, `struct SystemClock`, `struct Timestamp`, `mod time_util`
- C3 이름 검사: `fn is_identifier`, `fn is_valid_identifier`, `fn valid_identifier`
- C4 감사 해시 사슬: `prev_hash` 칸(행마다 앞 행 해시를 잇는 사슬)
찾으면 실패한다. 다만 docs/policy/waivers.json에 rule이 "ENG-REUSE-<번호>"로 시작하고 paths에 그 파일이 든 항목이 있으면
넘어간다(엔진 것이 들어오면 서비스가 옮기고 경로를 뺌). 예외가 있는데 그 파일에서 그 모양이 사라졌으면 예외를 지우라고
실패한다. 실패하면 `파일:줄: 이유`를 한 줄씩 내고 1로 끝난다.

사용: python3 -X utf8 scripts/ci/check-engine-reuse.py [저장소 루트]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist", "tests", "benches", "examples"}
# mookko-rust-qa 11-03 XC lint 후보 B를 반영해, 이름이 정확히 같을 때만 잡던 것을 쓰임 모양까지 넓혔다.
RULES: dict[str, tuple[re.Pattern[str], str]] = {
    "C1": (
        re.compile(r"\bconst\s+\w*MFA\w*\s*:|\"(recent_mfa_required|mfa_required)\""),
        "최근 MFA 기한·거절 코드는 엔진 공용 판정(C1 mookko_core::RecentMfaPolicy, 설정 rpc.server.staffRecentMfa, "
        "CallContext::require_recent_mfa(), StaffActor::has_recent_mfa, codes::RECENT_MFA_REQUIRED)을 쓰세요",
    ),
    "C2": (
        re.compile(
            r"\btrait\s+Clock\b|\bstruct\s+SystemClock\b|\bstruct\s+Timestamp\b|\bmod\s+time_util\b"
            r"|\bSystemTime::now\s*\(|\bTimestamp::now\s*\(|\bOffsetDateTime::now_utc\s*\("
            r"|\bfn\s+(utc_day|kst_day|today|civil_date|month_index|day_number)\s*\("
        ),
        "시계·시각은 주입한 엔진 공용 시계(C2 mookko_core::{Clock, SystemClock, FixedClock})를 쓰세요",
    ),
    "C3": (
        re.compile(
            r"\bfn\s+(is_identifier|is_valid_identifier|valid_identifier|is_slug|is_valid_slug)\b"
            r"|\\u\{(200[b-f]|202[a-e]|206[0-9]|feff)\}"
        ),
        "이름 검사·보이지 않는 문자 목록은 엔진 공용 이름 규칙(C3 mookko_core::NameKind::{StaffId, ActorId, Action, Slug, "
        "ReceiptKey, ServiceId, SqlIdentifier}, mookko_core::StaffId, mookko_core::has_hidden_characters)을 쓰세요",
    ),
    "C4": (
        re.compile(
            r"\b(prev_hash|previous_hash|entry_hash|verify_chain|ChainLink|audit_chain_(head|anchors))\b"
            r"|\bring::hmac\b|\bhmac::Key\b|\bHmac<"
        ),
        "감사 해시 사슬·HMAC은 엔진 공용 감사 원장(C4)·KeyedHasher를 쓰세요",
    ),
    "C7": (
        re.compile(r"\bfn\s+(rw|read_only)\s*\(\s*\)\s*->\s*TxOptions\b|\"SETTINGS\s+max_execution_time"),
        "트랜잭션 옵션·질의 기한은 엔진 공용 저장소 틀(C7 read_tx/write_tx, 남은 기한)을 쓰세요",
    ),
}


def code_lines(text: str):
    for no, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("//"):
            continue
        yield no, line.split("//", 1)[0] if "\"" not in line else line


def waivers(root: Path) -> dict[str, set[str]]:
    path = root / "docs" / "policy" / "waivers.json"
    if not path.exists():
        return {}
    out: dict[str, set[str]] = {}
    for w in json.loads(path.read_text(encoding="utf-8")).get("waivers", []):
        m = re.match(r"ENG-REUSE-(C\d)", str(w.get("rule", "")))
        if m:
            for p in w.get("paths", []):
                out.setdefault(p, set()).add(m.group(1))
    return out


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    waived = waivers(root)
    problems: list[str] = []
    found: dict[str, set[str]] = {}
    scanned = 0
    for base in (root / "crates" / "services", root / "crates" / "apps"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.rs")):
            rel = path.relative_to(root)
            if "src" not in rel.parts or any(p in SKIP_DIRS for p in rel.parts):
                continue
            scanned += 1
            key = rel.as_posix()
            for no, line in code_lines(path.read_text(encoding="utf-8")):
                for rule, (pattern, message) in RULES.items():
                    if pattern.search(line):
                        found.setdefault(key, set()).add(rule)
                        if rule not in waived.get(key, set()):
                            problems.append(f"{key}:{no}: {message}. 서비스가 공용 기능을 따로 만들지 않습니다({rule})")
    for key, rules in sorted(waived.items()):
        for rule in sorted(rules - found.get(key, set())):
            problems.append(f"docs/policy/waivers.json:1: {key}에 {rule} 복사본이 없어졌습니다. ENG-REUSE-{rule} 예외에서 빼세요")
    for p in problems:
        print(p)
    if problems:
        print(f"engine reuse check failed ({len(problems)} problems)")
        return 1
    print(f"engine reuse check passed ({scanned} files, {sum(len(v) for v in waived.values())} waived)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

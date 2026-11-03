"""포트·주소 하드코딩 검사 (AGENTS.md › 코드 규칙, 사용자 지시 2026-10-29).

포트·주소(IP, 호스트 이름, URL, host:port)는 코드나 상수에 두지 않고 JSON 설정에서만 읽는다.
Rust 소스(시험 포함)에서 아래를 찾으면 실패한다. 주석 줄(`//`로 시작)은 보지 않는다.
시험이 쓰는 주소는 시험용 JSON 파일(tests/fixtures/*.json)에 둔다.
예외: 주소가 아닌 표준 식별자 URI(예: OIDC 이벤트 이름)는 docs/policy/identifier-uris.json에 정확히 등록된 글자만 뺀다.
등록 항목에 칸(uri·standard·reason·expires·approvedBy)이 빠지거나 기한이 지나면 실패한다(R-CFG-1).
"""

from __future__ import annotations

import datetime
import os
import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()  # 인자를 주면 표본 폴더를 검사
IDENTIFIERS = ROOT / "docs" / "policy" / "identifier-uris.json"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # 0~255 네 덩어리이고 앞뒤에 글자·숫자·점이 붙지 않은 것만 주소로 봄(판 문자열 "1.2.3.4.5"·"v1.0.0.1"은 아님, PM 11-03).
    ("IPv4 literal", re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\w.])")),
    ("IPv6 loopback/any", re.compile(r"\"\[?::1?\]?(?::\d+)?\"")),
    ("localhost", re.compile(r"localhost", re.IGNORECASE)),
    ("URL", re.compile(r"\b[a-z][a-z0-9+.-]*://", re.IGNORECASE)),
    ("host:port literal", re.compile(r"\"[^\"\s]*:\d{2,5}\"")),
    ("address constructor", re.compile(r"\b(?:Ipv4Addr|Ipv6Addr|SocketAddrV4|SocketAddrV6|SocketAddr)::(?:new|LOCALHOST|UNSPECIFIED|BROADCAST|from)\b")),
    ("address tuple", re.compile(r"SocketAddr::from\s*\(\s*\(")),
]


def rust_files() -> list[Path]:
    files = []
    for base in (ROOT / "crates", ROOT / "acceptance"):
        if base.exists():
            files.extend(p for p in base.rglob("*.rs") if "target" not in p.parts)
    return sorted(files)


def registered_identifiers(problems: list[str]) -> list[str]:
    if not IDENTIFIERS.exists():
        return []
    data = json.loads(IDENTIFIERS.read_text(encoding="utf-8"))
    today = datetime.date.today()
    uris: list[str] = []
    for item in data.get("identifiers", []):
        missing = [k for k in ("uri", "standard", "reason", "expires", "approvedBy") if not item.get(k)]
        if missing:
            problems.append(f"identifier-uris.json: entry {item.get('uri')} is missing {missing}")
            continue
        try:
            expires = datetime.date.fromisoformat(item["expires"])
        except ValueError:
            problems.append(f"identifier-uris.json: {item['uri']} expires is not YYYY-MM-DD: {item['expires']}")
            continue
        if expires < today:
            problems.append(f"identifier-uris.json: {item['uri']} expired on {item['expires']}")
            continue
        uris.append(item["uri"])
    return uris


def main() -> int:
    problems: list[str] = []
    files = rust_files()
    identifiers = registered_identifiers(problems)
    for path in files:
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.lstrip().startswith("//"):
                continue
            for uri in identifiers:
                line = line.replace(uri, "")
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    rel = path.relative_to(ROOT).as_posix()
                    problems.append(f"{rel}:{no}: {label}: {line.strip()}")
    if problems:
        print("hard-coded endpoint check failed (move ports/addresses to JSON config):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"hard-coded endpoint check passed ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

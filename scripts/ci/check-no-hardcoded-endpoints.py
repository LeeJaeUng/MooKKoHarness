"""포트·주소 하드코딩 검사 (AGENTS.md › 코드 규칙, 사용자 지시 2026-10-29).

포트·주소(IP, 호스트 이름, URL, host:port)는 코드나 상수에 두지 않고 JSON 설정에서만 읽는다.
Rust 소스(시험 포함)에서 아래를 찾으면 실패한다. 주석 줄(`//`로 시작)은 보지 않는다.
시험이 쓰는 주소는 시험용 JSON 파일(tests/fixtures/*.json)에 둔다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("IPv4 literal", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("IPv6 loopback/any", re.compile(r"\"\[?::1?\]?(?::\d+)?\"")),
    ("localhost", re.compile(r"localhost", re.IGNORECASE)),
    ("URL", re.compile(r"\b[a-z][a-z0-9+.-]*://", re.IGNORECASE)),
    ("host:port literal", re.compile(r"\"[^\"\s]*:\d{2,5}\"")),
    ("address constructor", re.compile(r"\b(?:Ipv4Addr|Ipv6Addr|SocketAddrV4|SocketAddrV6|SocketAddr)::(?:new|LOCALHOST|UNSPECIFIED|BROADCAST|from)\b")),
    ("address tuple", re.compile(r"SocketAddr::from\s*\(\s*\(")),
]


def rust_files() -> list[Path]:
    files = []
    for base in (ROOT / "crates", ROOT / "apps"):
        if base.exists():
            files.extend(p for p in base.rglob("*.rs") if "target" not in p.parts)
    return sorted(files)


def main() -> int:
    problems: list[str] = []
    files = rust_files()
    for path in files:
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.lstrip().startswith("//"):
                continue
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

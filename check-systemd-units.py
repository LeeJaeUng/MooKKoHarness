"""운영 systemd unit 격리 검사(docs/architecture/host-security.md §3, 관문 HOST-01).

저장소 안의 모든 *.service 파일이 서비스 잠그기 지시어를 다 가지고 있는지 본다. 하나라도 빠지거나 값이 다르면 실패한다.
User가 root이거나 없으면 실패한다. 기한 있는 예외는 docs/policy/waivers.json(rule에 HOST-01, paths에 그 unit)에 있어야 한다.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WAIVERS = ROOT / "docs" / "policy" / "waivers.json"
SKIP_PARTS = {"target", ".git", ".claude", "node_modules", "data"}

# 지시어 → 있어야 할 값(None이면 값이 있기만 하면 됨, ""이면 빈 값).
REQUIRED: dict[str, str | None] = {
    "NoNewPrivileges": "yes",
    "CapabilityBoundingSet": "",
    "AmbientCapabilities": "",
    "ProtectSystem": "strict",
    "ProtectHome": "yes",
    "PrivateTmp": "yes",
    "PrivateDevices": "yes",
    "ProtectKernelTunables": "yes",
    "ProtectKernelModules": "yes",
    "ProtectKernelLogs": "yes",
    "ProtectControlGroups": "yes",
    "ProtectClock": "yes",
    "ProtectHostname": "yes",
    "RestrictAddressFamilies": "AF_UNIX AF_INET AF_INET6",
    "RestrictNamespaces": "yes",
    "RestrictSUIDSGID": "yes",
    "RestrictRealtime": "yes",
    "LockPersonality": "yes",
    "MemoryDenyWriteExecute": "yes",
    "SystemCallArchitectures": "native",
    "UMask": "0077",
    "WorkingDirectory": None,
}
# SystemCallFilter는 여러 줄: 허용 묶음과 거부 묶음이 둘 다 있어야 한다.
SYSCALL_ALLOW = "@system-service"
SYSCALL_DENY = {"@privileged", "@resources", "@mount", "@swap", "@reboot", "@raw-io", "@module", "@obsolete", "@cpu-emulation", "@debug"}


def units() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.service") if not SKIP_PARTS.intersection(p.relative_to(ROOT).parts))


def service_section(path: Path) -> dict[str, list[str]]:
    section = ""
    values: dict[str, list[str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section != "Service" or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values.setdefault(key.strip(), []).append(value.strip())
    return values


def waived(rel: str, today: datetime.date) -> bool:
    if not WAIVERS.exists():
        return False
    data = json.loads(WAIVERS.read_text(encoding="utf-8"))
    for item in data.get("waivers", []):
        if "HOST-01" in item.get("rule", "") and rel in item.get("paths", []):
            try:
                return datetime.date.fromisoformat(item["expires"]) >= today
            except (KeyError, ValueError):
                return False
    return False


def check_unit(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    values = service_section(path)
    problems: list[str] = []
    user = (values.get("User") or [""])[-1]
    if not user or user in {"root", "0"}:
        problems.append(f"{rel}: User가 없거나 root입니다")
    for key, want in REQUIRED.items():
        got = values.get(key)
        if got is None:
            problems.append(f"{rel}: {key}가 없습니다")
        elif want is not None and got[-1] != want:
            problems.append(f"{rel}: {key}={got[-1]} (기준 {want!r})")
    filters = values.get("SystemCallFilter", [])
    if SYSCALL_ALLOW not in filters:
        problems.append(f"{rel}: SystemCallFilter={SYSCALL_ALLOW}가 없습니다")
    denied = {group for f in filters if f.startswith("~") for group in f[1:].split()}
    missing = sorted(SYSCALL_DENY - denied)
    if missing:
        problems.append(f"{rel}: SystemCallFilter=~ 에 빠진 묶음 {missing}")
    return problems


def main() -> int:
    today = datetime.date.today()
    problems: list[str] = []
    files = units()
    waived_count = 0
    for path in files:
        found = check_unit(path)
        if found and waived(path.relative_to(ROOT).as_posix(), today):
            waived_count += 1
            continue
        problems.extend(found)
    if problems:
        print("systemd unit check failed (docs/architecture/host-security.md §3):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"systemd unit check passed ({len(files)} units, {waived_count} waived)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

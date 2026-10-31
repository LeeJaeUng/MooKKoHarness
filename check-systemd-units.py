"""운영 systemd unit 격리 검사(docs/architecture/host-security.md §3, 관문 HOST-01).

저장소 안의 모든 *.service 파일이 서비스 잠그기 지시어를 다 가지고 있는지 본다. 하나라도 빠지거나 값이 다르면 실패한다.
User가 root이거나 없으면 실패한다(이것은 예외로도 넘길 수 없다). Exec* 줄의 특권 접두어 +·!·!!도 같다(+는 격리를 모두 끄고,
!는 User를 무시하고 root로 돌린다 — systemd.service(5) 표 "Special executable prefixes", QA 2026-11-01 보통). 같은 지시어를 여러 줄 쓰면 systemd가 합치므로 실패로 본다
(SystemCallFilter만 허용·거부 줄을 따로 쓴다). drop-in(<unit>.service.d/*.conf)도 합쳐서 본다. .socket unit은 기준이 없어 통합 담당
확인 전까지 실패로 본다. 기한 있는 예외는 docs/policy/waivers.json(rule에 HOST-01, paths에 그 unit)에 있어야 한다.
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
# 명령을 받는 지시어와 그 앞에 붙을 수 있는 특수 접두어 글자(systemd.service(5)).
EXEC_KEYS = ("ExecCondition", "ExecStartPre", "ExecStart", "ExecStartPost", "ExecReload", "ExecStop", "ExecStopPost")
EXEC_PREFIX_CHARS = "@-:+!"


def tracked(pattern: str) -> list[Path]:
    return sorted(p for p in ROOT.rglob(pattern) if not SKIP_PARTS.intersection(p.relative_to(ROOT).parts))


def units() -> list[Path]:
    return tracked("*.service")


def service_section(path: Path) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    dropins = sorted((path.parent / f"{path.name}.d").glob("*.conf"))
    for file in [path, *dropins]:
        for key, vals in read_service(file).items():
            values.setdefault(key, []).extend(vals)
    return values


def read_service(path: Path) -> dict[str, list[str]]:
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


def exec_prefix(command: str) -> str:
    """Exec* 값 앞의 특수 접두어 묶음(@ - : + !)."""
    end = 0
    while end < len(command) and command[end] in EXEC_PREFIX_CHARS:
        end += 1
    return command[:end]


def unwaivable_problems(path: Path) -> list[str]:
    """예외로 넘길 수 없는 문제: root 실행, 특권 접두어."""
    rel = path.relative_to(ROOT).as_posix()
    values = service_section(path)
    problems: list[str] = []
    users = values.get("User") or [""]
    if not users[-1] or any(u in {"root", "0"} for u in users):
        problems.append(f"{rel}: User가 없거나 root입니다(예외 불가)")
    for key in EXEC_KEYS:
        for command in values.get(key, []):
            prefix = exec_prefix(command)
            if "+" in prefix or "!" in prefix:
                problems.append(f"{rel}: {key}의 특권 접두어 {prefix!r}는 격리나 User를 무시합니다(예외 불가)")
    return problems


def check_unit(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    values = service_section(path)
    problems: list[str] = []
    for key, want in REQUIRED.items():
        got = values.get(key)
        if got is None:
            problems.append(f"{rel}: {key}가 없습니다")
        elif len(got) > 1:
            problems.append(f"{rel}: {key}를 여러 줄(drop-in 포함) 썼습니다 — systemd가 합치므로 한 줄로")
        elif want is not None and got[0] != want:
            problems.append(f"{rel}: {key}={got[0]} (기준 {want!r})")
    filters = values.get("SystemCallFilter", [])
    allows = [f for f in filters if not f.startswith("~")]
    if allows != [SYSCALL_ALLOW]:
        problems.append(f"{rel}: 허용 SystemCallFilter는 {SYSCALL_ALLOW} 한 줄만이어야 합니다(지금 {allows})")
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
    for sock in tracked("*.socket"):
        problems.append(f"{sock.relative_to(ROOT).as_posix()}: .socket unit은 기준이 없습니다 — 통합 담당이 host-security.md에 기준을 넣을 때까지 금지")
    for path in files:
        problems.extend(unwaivable_problems(path))
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

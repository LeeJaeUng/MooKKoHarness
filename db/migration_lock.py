"""이관 잠금 (docs/policy/conventions/sql.md S-MIG-1).

출시 전(운영 DB가 없음)에는 이관 파일을 다시 써도 되지만, 출시 뒤에는 이미 낸 이관을 고치면 운영 DB의 이관 기록(SHA-256)과
어긋나 엔진 이관기가 시작을 거부하거나, 더 나쁘게는 DB마다 구조가 달라진다. 그래서 출시할 때 그 서비스 `migrations/` 파일의
SHA-256을 `migration-lock.json`에 적고, 그 뒤로는 잠긴 파일의 내용 바꾸기·지우기·이름 바꾸기를 막는다(새 파일 더하기만).
SHA-256은 엔진 `SchemaMigrator`와 같게 줄 끝을 `\\n`으로 맞춘 내용으로 계산한다.
잠금 기록: `python3 -X utf8 scripts/ci/db/migration_lint.py --lock <폴더> --decided-by <사용자 결정 근거> --launched-at YYYY-MM-DD`.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

LIST = Path(__file__).resolve().parent / "migration-lock.json"


def checksum(text: str) -> str:
    """엔진 이관기와 같은 SHA-256(줄 끝 `\\r\\n` → `\\n`)."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def load(path: Path = LIST) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def entries(data: dict) -> list[dict]:
    return list(data.get("launched", []))


def check(root: Path, data: dict) -> list[tuple[str, str]]:
    """잠긴 폴더마다 (경로, 문제). 칸이 빠졌거나, 잠긴 파일이 없어지거나 바뀌면 문제."""
    problems: list[tuple[str, str]] = []
    for entry in entries(data):
        missing = [k for k in ("dir", "launchedAt", "decidedBy", "files") if not entry.get(k)]
        if missing:
            problems.append((str(entry.get("dir", "migration-lock.json")), f"잠금 항목에 {missing} 칸이 없음"))
            continue
        directory = root / entry["dir"]
        for name, expected in sorted(entry["files"].items()):
            path = directory / name
            rel = f"{entry['dir']}/{name}"
            if not path.is_file():
                problems.append((rel, f"출시({entry['launchedAt']}) 때 잠긴 이관이 없어짐 — 지우기·이름 바꾸기 금지"))
            elif checksum(path.read_text(encoding="utf-8")) != expected:
                problems.append((rel, f"출시({entry['launchedAt']}) 때 잠긴 이관의 내용이 바뀜 — 새 이관 파일을 더함"))
        if directory.is_dir():
            for path in sorted(directory.glob("*.sql")):
                if path.name not in entry["files"]:
                    problems.append((f"{entry['dir']}/{path.name}", "출시된 서비스의 새 이관은 같은 커밋에서 잠금 목록에 더함(`migration_lint.py --lock`)"))
    return problems


def is_locked(data: dict, rel_dir: str) -> bool:
    return any(e.get("dir") == rel_dir for e in entries(data))


def record(root: Path, data: dict, rel_dir: str, decided_by: str, launched_at: datetime.date) -> dict:
    """폴더의 지금 이관 파일을 잠근 새 목록(이미 잠긴 폴더면 새 파일만 더함 — 옛 값은 바꾸지 않음)."""
    directory = root / rel_dir
    files = {p.name: checksum(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.sql"))}
    if not files:
        raise ValueError(f"{rel_dir}: 잠글 이관 파일이 없음")
    out = {k: v for k, v in data.items() if k != "launched"}
    launched = entries(data)
    for entry in launched:
        if entry.get("dir") == rel_dir:
            for name, value in files.items():
                entry["files"].setdefault(name, value)
            break
    else:
        launched.append({"dir": rel_dir, "launchedAt": launched_at.isoformat(), "decidedBy": decided_by, "files": files})
    out["launched"] = sorted(launched, key=lambda e: e["dir"])
    return out

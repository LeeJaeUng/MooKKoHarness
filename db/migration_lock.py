"""이관 잠금과 이관 다시 쓰기 확인 (docs/policy/conventions/sql.md S-MIG-1).

출시 뒤에는 이미 낸 이관을 고치면 운영 DB의 이관 기록(SHA-256)과 어긋나 엔진 이관기가 시작을 거부하거나 DB마다 구조가 달라진다.
- 잠금: 출시할 때 그 서비스 `migrations/` 파일의 SHA-256을 `migration-lock.json`에 적고, 그 뒤로는 잠긴 파일의 내용 바꾸기·지우기·
  이름 바꾸기와 잠그지 않은 새 파일을 막는다. SHA-256은 엔진 `SchemaMigrator`와 같게 `__SCHEMA__`를 따옴표 친 스키마 이름으로
  바꾸고 줄 끝을 `\\n`으로 맞춘 내용으로 계산한다(`migrate.rs` `add_dir`·`push`).
- 잠금 목록 줄이기 막기: git 기록에서 목록이 바뀔 때마다 앞 판의 항목·파일·값이 그대로 있는지 본다(지우거나 바꾸면 실패).
- 출시 전 다시 쓰기: 잠기지 않은 폴더라도 이미 커밋한 이관 파일을 바꾸거나 이름을 바꾸거나 지운 커밋은 본문에
  `출시 전 이관 다시 씀: <파일 이름>`이 있어야 한다(기준 커밋 `historyCheckedSince` 뒤만 봄 — 그 전 일은 이 규칙 전).
git 기록을 읽을 수 없으면(Windows 쪽 worktree를 WSL에서 여는 경우 등) "건너뜀(통과 아님)"을 출력하고,
`MOOKKO_REQUIRE_GIT_HISTORY=1`이면 실패한다(하네스 CI는 켬).
잠금 기록: `python3 -X utf8 scripts/ci/db/migration_lint.py --lock <폴더> --decided-by <사용자 결정 근거> --launched-at YYYY-MM-DD`.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
from pathlib import Path

LIST = Path(__file__).resolve().parent / "migration-lock.json"
LIST_REL = "scripts/ci/db/migration-lock.json"
REWRITE_MARK = "출시 전 이관 다시 씀:"
MIGRATION_GLOB = ":(glob)crates/**/migrations/*.sql"


def quoted(schema: str) -> str:
    """엔진 `SqlName::quoted`와 같은 따옴표 이름."""
    return '"' + schema.replace('"', '""') + '"'


def checksum(text: str, schema: str) -> str:
    """엔진 이관기와 같은 SHA-256: `__SCHEMA__` → 따옴표 친 스키마, 줄 끝 `\\r\\n` → `\\n`."""
    sql = text.replace("__SCHEMA__", quoted(schema)).replace("\r\n", "\n")
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def load(path: Path = LIST) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def entries(data: dict) -> list[dict]:
    return list(data.get("launched", []))


def check(root: Path, data: dict) -> list[tuple[str, str]]:
    """잠긴 폴더마다 (경로, 문제). 칸이 빠졌거나, 잠긴 파일이 없어지거나 바뀌거나, 잠그지 않은 새 파일이 있으면 문제."""
    problems: list[tuple[str, str]] = []
    for entry in entries(data):
        missing = [k for k in ("dir", "schema", "launchedAt", "decidedBy", "files") if not entry.get(k)]
        if missing:
            problems.append((str(entry.get("dir", LIST_REL)), f"잠금 항목에 {missing} 칸이 없음"))
            continue
        directory = root / entry["dir"]
        for name, expected in sorted(entry["files"].items()):
            path = directory / name
            rel = f"{entry['dir']}/{name}"
            if not path.is_file():
                problems.append((rel, f"출시({entry['launchedAt']}) 때 잠긴 이관이 없어짐 — 지우기·이름 바꾸기 금지"))
            elif checksum(path.read_text(encoding="utf-8"), entry["schema"]) != expected:
                problems.append((rel, f"출시({entry['launchedAt']}) 때 잠긴 이관의 내용이 바뀜 — 새 이관 파일을 더함"))
        if directory.is_dir():
            for path in sorted(directory.glob("*.sql")):
                if path.name not in entry["files"]:
                    problems.append((f"{entry['dir']}/{path.name}", "출시된 서비스의 새 이관은 같은 커밋에서 잠금 목록에 더함(`migration_lint.py --lock`)"))
    return problems


def record(root: Path, data: dict, rel_dir: str, schema: str, decided_by: str, launched_at: datetime.date) -> dict:
    """폴더의 지금 이관 파일을 잠근 새 목록(이미 잠긴 폴더면 새 파일만 더함 — 옛 값은 바꾸지 않음)."""
    directory = root / rel_dir
    files = {p.name: checksum(p.read_text(encoding="utf-8"), schema) for p in sorted(directory.glob("*.sql"))}
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
        launched.append(
            {"dir": rel_dir, "schema": schema, "launchedAt": launched_at.isoformat(), "decidedBy": decided_by, "files": files}
        )
    out["launched"] = sorted(launched, key=lambda e: e["dir"])
    return out


# ---- 기록 비교(순수 함수, 시험이 직접 부름) ----
def shrink_findings(versions: list[tuple[str, dict]]) -> list[tuple[str, str]]:
    """잠금 목록의 판들(오래된 것부터)에서 앞 판의 항목·파일·값이 뒤 판에서 빠지거나 바뀌면 문제."""
    problems: list[tuple[str, str]] = []
    for (_, before), (label, after) in zip(versions, versions[1:]):
        later = {e.get("dir"): e for e in entries(after)}
        for entry in entries(before):
            now = later.get(entry.get("dir"))
            if now is None:
                problems.append((LIST_REL, f"{label}: 잠긴 폴더 `{entry.get('dir')}` 항목을 지움(잠금 풀기는 사용자 결정)"))
                continue
            for key in ("schema", "launchedAt", "decidedBy"):
                if now.get(key) != entry.get(key):
                    problems.append((LIST_REL, f"{label}: `{entry.get('dir')}`의 {key}를 바꿈"))
            for name, value in entry.get("files", {}).items():
                if now.get("files", {}).get(name) != value:
                    problems.append((LIST_REL, f"{label}: 잠긴 이관 `{entry.get('dir')}/{name}`을 목록에서 지우거나 값을 바꿈"))
    return problems


def rewrite_findings(commits: list[tuple[str, str, list[tuple[str, str]]]], launched_dirs: set[str]) -> list[tuple[str, str]]:
    """커밋(SHA, 본문, [(상태, 경로)]) 가운데 잠기지 않은 폴더의 이관을 고친(M)·이름 바꾼(R)·지운(D) 것은 본문 표시가 있어야 함."""
    problems: list[tuple[str, str]] = []
    for sha, body, changes in commits:
        for status, path in changes:
            if status[:1] not in ("M", "R", "D"):
                continue
            if any(path.startswith(d.rstrip("/") + "/") for d in launched_dirs):
                continue  # 잠긴 폴더는 잠금 검사가 막음
            name = path.rsplit("/", 1)[-1]
            if REWRITE_MARK not in body or name not in body:
                problems.append((path, f"커밋 {sha[:10]}이 이미 커밋한 이관을 바꿈 — 본문에 `{REWRITE_MARK} {name}`과 이유(출시 전 예외, sql.md S-MIG-1)"))
    return problems


# ---- git ----
def git(root: Path, *args: str) -> str | None:
    """git 출력. git이 없거나 저장소를 읽을 수 없으면 None."""
    try:
        done = subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, encoding="utf-8")
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout


def history_commits(root: Path, since: str) -> list[tuple[str, str, list[tuple[str, str]]]] | None:
    out = git(root, "log", "-M", "--format=%x1e%H%x1f%B%x1f", "--name-status", f"{since}..HEAD", "--", MIGRATION_GLOB)
    if out is None:
        return None
    commits: list[tuple[str, str, list[tuple[str, str]]]] = []
    for record_text in out.split("\x1e"):
        if not record_text.strip():
            continue
        sha, body, files = (record_text.split("\x1f") + ["", ""])[:3]
        changes: list[tuple[str, str]] = []
        for line in files.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                changes.append((parts[0], parts[-1]))
                if parts[0].startswith("R") and len(parts) == 3:
                    changes.append(("D", parts[1]))
        commits.append((sha.strip(), body, changes))
    return commits


def lock_versions(root: Path, since: str, current: dict) -> list[tuple[str, dict]] | None:
    shas = git(root, "log", "--reverse", "--format=%H", f"{since}..HEAD", "--", LIST_REL)
    if shas is None:
        return None
    versions: list[tuple[str, dict]] = []
    base = git(root, "show", f"{since}:{LIST_REL}")
    versions.append((f"기준 {since[:10]}", json.loads(base) if base else {"launched": []}))
    for sha in shas.split():
        text = git(root, "show", f"{sha}:{LIST_REL}")
        versions.append((f"커밋 {sha[:10]}", json.loads(text) if text else {"launched": []}))
    versions.append(("작업 사본", current))
    return versions


def uncommitted_rewrites(root: Path) -> list[str]:
    """커밋 전 작업 사본에서 이미 커밋한 이관을 바꾼 파일(커밋할 때 본문 표시가 필요하다는 알림용)."""
    out = git(root, "status", "--porcelain", "--", MIGRATION_GLOB) or ""
    return [line[3:] for line in out.splitlines() if line[:2].strip() in ("M", "R", "D", "MM", "RM")]

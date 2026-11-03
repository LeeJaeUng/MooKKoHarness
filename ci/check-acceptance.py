"""인수 시험 관문 (docs/policy/gates.md ACC-01, PM 사용자 대행 2026-11-03 CM1).

acceptance/services.json의 서비스마다 acceptance/runs/<id>/*.json 실행 기록을 본다.
- 파일 이름: <UTC YYYYMMDDTHHMMZ>-<커밋 앞 7자>.json
- 기록 형식: service·commit(40자, 지금 HEAD의 조상)·command·startedAt(ISO)·passed·failed·skipped·engine.
- 판정은 서비스마다 **가장 최근 기록**(startedAt) 하나로 한다(QA f93973a: 통과 기록이 하나라도 있으면 통과로 보던 구멍).
  passed > 0, failed == 0, skipped == 0이고 commit이 HEAD의 조상이어야 통과. 건너뜀은 통과가 아님.
- 통과가 아니면: enforce가 true인 서비스는 실패, false인 서비스는 경고만(due가 지났으면 경고에 적음).
- 형식이 틀린 기록, services.json에 없는 runs 폴더, services.json 칸 오류는 enforce와 상관없이 실패.
실패하면 `파일:줄: 이유`를 한 줄씩 내고 1로 끝난다. 경고는 `경고:`로 시작한다.

사용: python3 -X utf8 ci/check-acceptance.py [저장소 루트]
"""

from __future__ import annotations

import datetime
import os
import json
import re
import subprocess
import sys
from pathlib import Path

FIELDS = {"service": str, "commit": str, "command": str, "startedAt": str, "passed": int, "failed": int, "skipped": int, "engine": str}
SERVICE_FIELDS = {"id": str, "owner": str, "enforce": bool}
RUN_NAME = re.compile(r"\d{8}T\d{4}Z-[0-9a-f]{7}\.json")


def git(root: Path, *args: str) -> int:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8").returncode


def read_run(root: Path, path: Path, service: str, problems: list[str]) -> dict | None:
    """형식이 맞으면 기록을, 틀리면 문제를 적고 None을 돌려준다."""
    rel = path.relative_to(root).as_posix()
    if not RUN_NAME.fullmatch(path.name):
        problems.append(f"{rel}:1: 파일 이름은 <UTC YYYYMMDDTHHMMZ>-<커밋 7자>.json이어야 합니다")
        return None
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        problems.append(f"{rel}:1: JSON이 아닙니다: {e}")
        return None
    for key, kind in FIELDS.items():
        if not isinstance(run.get(key), kind) or isinstance(run.get(key), bool):
            problems.append(f"{rel}:1: {key} 칸이 없거나 형이 {kind.__name__}가 아닙니다")
            return None
    if run["service"] != service:
        problems.append(f"{rel}:1: service {run['service']}가 폴더 {service}와 다릅니다")
        return None
    if not re.fullmatch(r"[0-9a-f]{40}", run["commit"]) or not path.name.endswith(f"-{run['commit'][:7]}.json"):
        problems.append(f"{rel}:1: commit은 40자 해시이고 파일 이름 끝 7자와 같아야 합니다")
        return None
    try:
        run["_at"] = datetime.datetime.fromisoformat(run["startedAt"].replace("Z", "+00:00"))
    except ValueError:
        problems.append(f"{rel}:1: startedAt이 ISO 시각이 아닙니다")
        return None
    run["_rel"] = rel
    return run


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    plan_path = root / "acceptance" / "services.json"
    problems: list[str] = []
    warnings: list[str] = []
    try:
        services = json.loads(plan_path.read_text(encoding="utf-8"))["services"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"acceptance/services.json:1: 읽지 못했습니다: {e}")
        print("acceptance check failed (1 problems)")
        return 1
    today = datetime.date.today()
    known: set[str] = set()
    for svc in services:
        bad = [k for k, kind in SERVICE_FIELDS.items() if not isinstance(svc.get(k), kind)]
        due = svc.get("due")
        if due is not None:
            try:
                datetime.date.fromisoformat(due)
            except (TypeError, ValueError):
                bad.append("due")
        if bad:
            problems.append(f"acceptance/services.json:1: {svc.get('id')} 항목의 칸이 틀렸습니다: {bad}")
            continue
        sid = svc["id"]
        known.add(sid)
        runs = [r for r in (read_run(root, p, sid, problems) for p in sorted((root / "acceptance" / "runs" / sid).glob("*.json"))) if r]
        latest = max(runs, key=lambda r: r["_at"], default=None)
        verdict = ""
        if latest is None:
            verdict = "인수 시험 기록이 없습니다"
        elif not (latest["passed"] > 0 and latest["failed"] == 0 and latest["skipped"] == 0):
            verdict = f"가장 최근 기록 {latest['_rel']}이 통과가 아닙니다(통과 {latest['passed']}, 실패 {latest['failed']}, 건너뜀 {latest['skipped']})"
        elif git(root, "merge-base", "--is-ancestor", latest["commit"], "HEAD") != 0:
            verdict = f"가장 최근 기록 {latest['_rel']}의 commit {latest['commit'][:12]}이 지금 HEAD의 조상이 아닙니다"
        if not verdict:
            continue
        late = due is not None and datetime.date.fromisoformat(due) < today
        message = f"{sid}: {verdict}(담당 {svc['owner']}, 기한 {due or '미정'}{', 지남' if late else ''})"
        if svc["enforce"]:
            problems.append(f"acceptance/services.json:1: {message}")
        else:
            warnings.append(message)
    runs_dir = root / "acceptance" / "runs"
    if runs_dir.exists():
        for folder in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
            if folder.name not in known:
                problems.append(f"{folder.relative_to(root).as_posix()}/:1: services.json에 없는 서비스의 기록 폴더입니다")
    for w in warnings:
        print(f"경고: {w}")
    for p in problems:
        print(p)
    if problems:
        print(f"acceptance check failed ({len(problems)} problems)")
        return 1
    print(f"acceptance check passed ({len(services)} services, {len(warnings)} warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

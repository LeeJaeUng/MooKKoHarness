"""인수 시험 관문 (docs/policy/gates.md ACC-01, PM 사용자 대행 2026-11-03 CM1).

acceptance/services.json의 서비스마다 acceptance/runs/<id>/*.json 실행 기록을 본다.
- 기록 형식: service·commit(40자, 저장소 이력에 있음)·command·startedAt·passed·failed·skipped·engine.
- 통과 기록: passed > 0, failed == 0, skipped == 0. 건너뜀은 통과가 아님.
- 통과 기록이 없으면: enforce가 true인 서비스는 실패, false인 서비스는 경고만(due가 지났으면 경고에 적음).
- 형식이 틀린 기록은 enforce와 상관없이 실패.
실패하면 `파일:줄: 이유`를 한 줄씩 내고 1로 끝난다. 경고는 `경고:`로 시작한다.

사용: python3 -X utf8 scripts/ci/check-acceptance.py [저장소 루트]
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

FIELDS = {"service": str, "commit": str, "command": str, "startedAt": str, "passed": int, "failed": int, "skipped": int, "engine": str}


def commit_known(root: Path, commit: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=root, capture_output=True, text=True
    )
    return result.returncode == 0


def check_run(root: Path, path: Path, service: str, problems: list[str]) -> bool:
    rel = path.relative_to(root).as_posix()
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        problems.append(f"{rel}:1: JSON이 아닙니다: {e}")
        return False
    for key, kind in FIELDS.items():
        if not isinstance(run.get(key), kind) or isinstance(run.get(key), bool):
            problems.append(f"{rel}:1: {key} 칸이 없거나 형이 {kind.__name__}가 아닙니다")
            return False
    if run["service"] != service:
        problems.append(f"{rel}:1: service {run['service']}가 폴더 {service}와 다릅니다")
        return False
    if not re.fullmatch(r"[0-9a-f]{40}", run["commit"]):
        problems.append(f"{rel}:1: commit은 40자 해시여야 합니다")
        return False
    if not commit_known(root, run["commit"]):
        problems.append(f"{rel}:1: commit {run['commit'][:12]}이 저장소 이력에 없습니다")
        return False
    try:
        datetime.datetime.fromisoformat(run["startedAt"].replace("Z", "+00:00"))
    except ValueError:
        problems.append(f"{rel}:1: startedAt이 ISO 시각이 아닙니다")
        return False
    return run["passed"] > 0 and run["failed"] == 0 and run["skipped"] == 0


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    plan = json.loads((root / "acceptance" / "services.json").read_text(encoding="utf-8"))
    today = datetime.date.today()
    problems: list[str] = []
    warnings: list[str] = []
    for svc in plan["services"]:
        sid = svc["id"]
        runs = sorted((root / "acceptance" / "runs" / sid).glob("*.json"))
        passed = [r for r in runs if check_run(root, r, sid, problems)]
        if passed:
            continue
        due = svc.get("due")
        late = due is not None and datetime.date.fromisoformat(due) < today
        message = f"{sid}: 통과한 인수 시험 기록이 없습니다(담당 {svc['owner']}, 기한 {due or '미정'}{', 지남' if late else ''})"
        if svc.get("enforce"):
            problems.append(f"acceptance/services.json:1: {message}")
        else:
            warnings.append(message)
    for w in warnings:
        print(f"경고: {w}")
    for p in problems:
        print(p)
    if problems:
        print(f"acceptance check failed ({len(problems)} problems)")
        return 1
    print(f"acceptance check passed ({len(plan['services'])} services, {len(warnings)} warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

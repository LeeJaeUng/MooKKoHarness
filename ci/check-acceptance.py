"""인수 시험 관문 (docs/policy/gates.md ACC-01, PM 사용자 대행 2026-11-03 CM1).

acceptance/services.json의 서비스마다 acceptance/runs/<id>/*.json 실행 기록을 본다.
- 파일 이름: <UTC YYYYMMDDTHHMMZ>-<커밋 앞 7자>.json
- 기록 형식: service·commit(40자, 지금 HEAD의 조상)·command·startedAt(ISO)·passed·failed·skipped·engine.
- 판정은 서비스마다 **가장 최근 기록**(startedAt) 하나로 한다(QA f93973a: 통과 기록이 하나라도 있으면 통과로 보던 구멍).
  passed > 0, failed == 0, skipped == 0이고 commit이 HEAD의 조상이어야 통과. 건너뜀은 통과가 아님.
- 통과가 아니면: enforce가 true인 서비스는 실패, false인 서비스는 경고만(due가 지났으면 경고에 적음).
- 형식이 틀린 기록, services.json에 없는 runs 폴더, services.json 칸 오류는 enforce와 상관없이 실패.
- 신선도(qa-services CA-9·rust-qa 11-14, 백로그 9x): 통과한 가장 최근 기록의 commit 뒤로 그 서비스 경로가 바뀌었으면 경고
  경로는 services.json 항목의 `paths`(목록), 없으면 crates/services/<id>·crates/apps/mookko-<id>·acceptance/<id>.
  `--l4`(출시 관문)에서는 실행 파일이 빌드되는 범위로 넓혀(qa-services CA-12: 엔진·어댑터·proto·Cargo.lock만 바뀐 판도 막아야) 저장소 전체에서
  docs/·*.md·acceptance/runs/·다른 서비스의 코드(crates/services/<다른 id>·crates/apps/mookko-<다른 id>·acceptance/<다른 id>)만 빼고 보며,
  바뀐 것이 있으면 enforce 서비스는 실패.
실패하면 `파일:줄: 이유`를 한 줄씩 내고 1로 끝난다. 경고는 `경고:`로 시작한다.

사용: python3 -X utf8 ci/check-acceptance.py [저장소 루트] [--l4]
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


def changed_since(root: Path, commit: str, paths: list[str]) -> list[str] | None:
    """commit 뒤로(그 commit..HEAD) paths 아래에서 바뀐 파일. git을 못 읽으면 None."""
    done = subprocess.run(["git", "diff", "--name-only", f"{commit}..HEAD", "--", *paths], cwd=root,
                          capture_output=True, text=True, encoding="utf-8")
    return [line for line in done.stdout.splitlines() if line.strip()] if done.returncode == 0 else None


RELEASE_PATHSPEC = [".", ":(exclude)docs", ":(exclude,glob)**/*.md", ":(exclude)acceptance/runs"]
OTHER_SERVICE = re.compile(r"^(?:crates/services/([^/]+)/|crates/apps/mookko-([^/]+)/|acceptance/([^/]+)/|config/mookko-([a-z0-9-]+?)[.-])")


def release_changes(root: Path, commit: str, sid: str) -> list[str] | None:
    """L4 신선도 범위(CA-12): 저장소 전체에서 docs/·*.md·acceptance/runs/를 빼고, 다른 서비스의 코드·설정 예시(crates/services/<x>·
    crates/apps/mookko-<x>·acceptance/<x>·config/mookko-<x>…, x ≠ 그 서비스, acceptance/common은 남김)도 뺀 바뀐 파일."""
    changed = changed_since(root, commit, RELEASE_PATHSPEC)
    if changed is None:
        return None
    kept = []
    for path in changed:
        m = OTHER_SERVICE.match(path)
        owner = next((g for g in m.groups() if g), None) if m else None
        if owner is None or owner in (sid, "common"):
            kept.append(path)
    return kept


def service_paths(svc: dict) -> list[str]:
    paths = svc.get("paths")
    if isinstance(paths, list) and paths and all(isinstance(x, str) and x for x in paths):
        return paths
    sid = svc["id"]
    return [f"crates/services/{sid}", f"crates/apps/mookko-{sid}", f"acceptance/{sid}"]


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
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    l4 = "--l4" in sys.argv[1:]
    root = Path(args[0]).resolve() if args else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
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
            changed = (release_changes(root, latest["commit"], sid) if (l4 and svc["enforce"])
                       else changed_since(root, latest["commit"], service_paths(svc)))
            if changed is None and os.environ.get("MOOKKO_REQUIRE_GIT_HISTORY") == "1":
                # git을 못 읽으면 신선도를 볼 수 없으므로 check-all(REQUIRE=1)에서는 실패(rust-qa 11-14 낮음 2)
                problems.append(f"acceptance/services.json:1: {sid}: 기록 {latest['_rel']} 뒤 바뀐 파일을 git으로 읽지 못해 신선도를 볼 수 없습니다(CA-9)")
            if changed:
                scope = "실행 파일 범위(L4)" if (l4 and svc["enforce"]) else "서비스 경로"
                stale = (f"{sid}: 가장 최근 통과 기록 {latest['_rel']}(commit {latest['commit'][:12]}) 뒤로 {scope} 파일 {len(changed)}개가 "
                         f"바뀌었습니다(예: {changed[0]}) — 새 판으로 인수 시험을 다시 돌려 기록하세요(CA-9)")
                if l4 and svc["enforce"]:
                    problems.append(f"acceptance/services.json:1: {stale}")
                else:
                    warnings.append(stale)
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

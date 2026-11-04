"""보안 파일 담당 강제 (하네스 policy/conventions/security.md SC-REG-3, 보안 담당 결정 2026-11-04 755f466, mookko-rust-qa 추가 5).

제품 docs/coordination/owners.json에서 주인이 "보안"인 경로(등록부·검토 기록·보안 설계서·규약·스킬)는 보안 담당 커밋으로만 바꾼다.
기준 판(MOOKKO_REGISTER_BASE, 기본 foundation/engine)..HEAD 사이의 머지 아닌 커밋마다, 그 커밋이 바꾼 파일 가운데 주인이 "보안"인 것이
있으면 그 커밋이 보안 브랜치(MOOKKO_SECURITY_BRANCH, 기본 claude/security와 origin/claude/security 중 하나)의 조상이어야 한다.
예외: 하네스 사본 자리(docs/policy/gates.*, docs/policy/conventions/, .claude/skills/)의 파일이 고정 판 하네스 정본과 같으면(통합 담당의
판 올림 사본 맞추기) 통과. 검사 폴더가 git 최상위가 아니면(표본) 보지 않고, git·기준 판·보안 브랜치를 읽지 못하면 "건너뜀"을 내고
MOOKKO_REQUIRE_GIT_HISTORY=1이면 실패. 실패는 `파일:1: 이유`.

사용: python3 -X utf8 ci/check-owner-paths.py [저장소 루트] [하네스 루트]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

OWNER = "보안"
COPIES = {"docs/policy/gates.md": "policy/gates.md", "docs/policy/gates.json": "policy/gates.json",
          "docs/policy/conventions/": "policy/conventions/", ".claude/skills/": "skills/"}


def git(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")
    return result.stdout if result.returncode == 0 else None


def owner_of(rules: list[dict], path: str) -> str | None:
    best = None
    for rule in rules:
        p = rule.get("path", "")
        if (p.endswith("/") and path.startswith(p)) or path == p:
            if best is None or len(p) > len(best[0]):
                best = (p, rule.get("owner"))
    return best[1] if best else None


def harness_copy_same(root: Path, harness: Path, path: str) -> bool:
    for prefix, target in COPIES.items():
        if path == prefix or (prefix.endswith("/") and path.startswith(prefix)):
            canon = harness / (target + path[len(prefix):] if prefix.endswith("/") else target)
            mine = root / path
            if canon.is_file() and mine.is_file():
                return canon.read_bytes().replace(b"\r\n", b"\n") == mine.read_bytes().replace(b"\r\n", b"\n")
            return False
    return False


def main(argv: list[str]) -> int:
    root = Path(argv[0]).resolve() if argv else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    harness = Path(argv[1]).resolve() if len(argv) > 1 else Path(os.environ.get("MOOKKO_HARNESS_DIR") or Path(__file__).resolve().parents[1])
    required = os.environ.get("MOOKKO_REQUIRE_GIT_HISTORY") == "1"

    def skip(why: str) -> int:
        if required:
            print(f"docs/coordination/owners.json:1: 보안 파일 담당을 대조하지 못했습니다({why})")
            print("owner path check failed (1 problems)")
            return 1
        print(f"owner path check skipped(통과 아님): {why}")
        return 0

    top = git(root, "rev-parse", "--show-toplevel")
    if top is None:
        return skip("git을 읽지 못함")
    if Path(top.strip()).resolve() != root:
        print("owner path check passed (표본, git 최상위 아님)")
        return 0
    try:
        rules = json.loads((root / "docs" / "coordination" / "owners.json").read_text(encoding="utf-8")).get("rules", [])
    except (OSError, ValueError) as e:
        print(f"docs/coordination/owners.json:1: 읽지 못했습니다: {e}")
        return 1
    base = os.environ.get("MOOKKO_REGISTER_BASE") or "foundation/engine"
    if git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}") is None:
        return skip(f"기준 판 {base}를 읽지 못함")
    names = [os.environ["MOOKKO_SECURITY_BRANCH"]] if os.environ.get("MOOKKO_SECURITY_BRANCH") else ["claude/security", "origin/claude/security"]
    branches = [b for b in names if git(root, "rev-parse", "--verify", "--quiet", f"{b}^{{commit}}") is not None]
    commits = (git(root, "rev-list", "--no-merges", f"{base}..HEAD") or "").split()
    problems: list[str] = []
    for commit in commits:
        files = (git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit) or "").splitlines()
        owned = [f for f in files if owner_of(rules, f) == OWNER]
        if not owned:
            continue
        if any(subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", commit, b]).returncode == 0 for b in branches):
            continue
        subject = (git(root, "log", "-1", "--format=%s", commit) or "").strip()[:60]
        for f in owned:
            if harness_copy_same(root, harness, f):
                continue  # 판 올림 사본 맞추기(고정 판 정본과 같음)
            problems.append(f"{f}:1: 주인이 {OWNER}인 파일을 보안 브랜치 밖 커밋 {commit[:7]}({subject})이 바꿨습니다(SC-REG-3)")
    if not branches and problems:
        return skip("보안 브랜치를 읽지 못함")
    for p in problems:
        print(p)
    if problems:
        print(f"owner path check failed ({len(problems)} problems)")
        return 1
    print(f"owner path check passed ({len(commits)} commits since {base})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

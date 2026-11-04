"""보안 파일 담당 강제 (하네스 policy/conventions/security.md SC-REG-3, 보안 담당 결정 2026-11-04 755f466, mookko-rust-qa 추가 5·6).

제품 docs/coordination/owners.json에서 주인이 "보안"인 경로(등록부·검토 기록·보안 설계서·규약·스킬)는 보안 담당 커밋으로만 바꾼다.
기준 판(MOOKKO_REGISTER_BASE, 기본 foundation/engine)..HEAD 사이의 커밋마다, 그 커밋이 바꾼 파일 가운데 주인이 "보안"인 것이
있으면 그 커밋이 보안 브랜치(MOOKKO_SECURITY_BRANCH, 기본 claude/security와 origin/claude/security 중 하나)의 조상이어야 한다.
- 머지 커밋도 본다(추가 6 ①): `diff-tree --cc`로 어느 부모와도 다른 파일(충돌을 풀며 고친 파일)만 그 머지가 바꾼 것으로 센다.
- 주인 규칙은 기준 판과 HEAD 규칙을 합친다(추가 6 ③): 같은 범위에서 owners.json의 보안 줄을 지워도 보호가 꺼지지 않는다.
  owners.json의 보안 줄(경로 목록)을 바꾸는 커밋도 보안 커밋이어야 한다.
- git 명령이 실패하면 빈 목록으로 통과시키지 않고 "건너뜀"(MOOKKO_REQUIRE_GIT_HISTORY=1이면 실패)으로 낸다.
예외: 하네스 사본 자리(docs/policy/gates.*, docs/policy/conventions/, .claude/skills/)의 파일이 고정 판 하네스 정본과 같으면(통합 담당의
판 올림 사본 맞추기) 통과. 검사 폴더가 git 최상위가 아니면(표본) 보지 않는다. 실패는 `파일:1: 이유`.
보안 브랜치는 merge로만 받는다(rebase하면 조상 관계가 끊겨 거짓 실패가 난다).
- 앞으로만(보안 담당 4e9b032 SC-REG-3 ①, GitHub 브랜치 보호를 못 걸어서): 기준 판 기록에서 보안 경로(사본 자리 뺌)를 바꾼 머지 아닌
  커밋은 모두 지금 보안 브랜치(origin/claude/security가 있으면 그것)의 조상이어야 한다. rebase·force-push·지우기로 다시 쓰면 실패.
- 하네스 사본 같음은 작업 트리가 아니라 그 커밋의 파일 내용으로 비교한다(QA 55628d2 낮음).

사용: python3 -X utf8 ci/check-owner-paths.py [저장소 루트] [하네스 루트]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

OWNER = "보안"
OWNERS_FILE = "docs/coordination/owners.json"
COPIES = {"docs/policy/gates.md": "policy/gates.md", "docs/policy/gates.json": "policy/gates.json",
          "docs/policy/conventions/": "policy/conventions/", ".claude/skills/": "skills/"}


class GitError(Exception):
    pass


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args[:3])}: {result.stderr.strip()[:200]}")
    return result.stdout


def has_ref(root: Path, ref: str) -> bool:
    try:
        git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        return True
    except GitError:
        return False


def owner_of(rules: list[dict], path: str) -> str | None:
    best = None
    for rule in rules:
        p = rule.get("path", "")
        if (p.endswith("/") and path.startswith(p)) or path == p:
            if best is None or len(p) > len(best[0]):
                best = (p, rule.get("owner"))
    return best[1] if best else None


def rules_at(root: Path, commit: str) -> list[dict]:
    """그 커밋의 owners.json 규칙. 파일이 없으면 빈 목록, 읽었는데 깨졌으면 GitError."""
    try:
        text = git(root, "show", f"{commit}:{OWNERS_FILE}")
    except GitError:
        return []
    try:
        return json.loads(text).get("rules", [])
    except ValueError as e:
        raise GitError(f"{commit[:7]}의 {OWNERS_FILE}를 읽지 못함: {e}") from e


def security_paths(rules: list[dict]) -> frozenset[str]:
    return frozenset(r.get("path", "") for r in rules if r.get("owner") == OWNER)


def is_copy(path: str) -> bool:
    return any(path == prefix or (prefix.endswith("/") and path.startswith(prefix)) for prefix in COPIES)


def harness_copy_same(root: Path, harness: Path, commit: str, path: str) -> bool:
    """그 커밋의 파일 내용이 고정 판 하네스 정본과 같은지(판 올림 사본 맞추기)."""
    for prefix, target in COPIES.items():
        if path == prefix or (prefix.endswith("/") and path.startswith(prefix)):
            canon = harness / (target + path[len(prefix):] if prefix.endswith("/") else target)
            mine = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{path}"], capture_output=True)
            if canon.is_file() and mine.returncode == 0:
                return canon.read_bytes().replace(b"\r\n", b"\n") == mine.stdout.replace(b"\r\n", b"\n")
            return False
    return False


def changed_files(root: Path, commit: str, parents: list[str]) -> list[str]:
    """그 커밋이 바꾼 파일. 머지는 어느 부모와도 다른 파일만(--cc)."""
    if len(parents) > 1:
        return git(root, "diff-tree", "--cc", "--no-commit-id", "--name-only", "-r", commit).splitlines()
    return git(root, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", commit).splitlines()


def main(argv: list[str]) -> int:
    root = Path(argv[0]).resolve() if argv else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    harness = Path(argv[1]).resolve() if len(argv) > 1 else Path(os.environ.get("MOOKKO_HARNESS_DIR") or Path(__file__).resolve().parents[1])
    required = os.environ.get("MOOKKO_REQUIRE_GIT_HISTORY") == "1"

    def skip(why: str) -> int:
        if required:
            print(f"{OWNERS_FILE}:1: 보안 파일 담당을 대조하지 못했습니다({why})")
            print("owner path check failed (1 problems)")
            return 1
        print(f"owner path check skipped(통과 아님): {why}")
        return 0

    try:
        top = git(root, "rev-parse", "--show-toplevel")
    except GitError:
        return skip("git을 읽지 못함")
    if Path(top.strip()).resolve() != root:
        print("owner path check passed (표본, git 최상위 아님)")
        return 0
    try:
        head_rules = json.loads((root / OWNERS_FILE).read_text(encoding="utf-8")).get("rules", [])
    except (OSError, ValueError) as e:
        print(f"{OWNERS_FILE}:1: 읽지 못했습니다: {e}")
        return 1
    base = os.environ.get("MOOKKO_REGISTER_BASE") or "foundation/engine"
    if not has_ref(root, base):
        return skip(f"기준 판 {base}를 읽지 못함")
    names = [os.environ["MOOKKO_SECURITY_BRANCH"]] if os.environ.get("MOOKKO_SECURITY_BRANCH") else ["claude/security", "origin/claude/security"]
    branches = [b for b in names if has_ref(root, b)]
    problems: list[str] = []
    try:
        base_rules = rules_at(root, base)  # 기준 판과 HEAD 규칙을 합쳐 판정(어느 쪽이든 보안이면 보안)
        commits = git(root, "rev-list", "--parents", f"{base}..HEAD").splitlines()
        for line in commits:
            commit, *parents = line.split()
            files = changed_files(root, commit, parents)
            owned = [f for f in files if OWNER in (owner_of(base_rules, f), owner_of(head_rules, f))]
            if OWNERS_FILE in files and OWNERS_FILE not in owned:
                mine = security_paths(rules_at(root, commit))
                if all(security_paths(rules_at(root, p)) != mine for p in parents) and (parents or mine):
                    owned.append(OWNERS_FILE)  # 보안 줄(경로 목록)을 바꿈
            if not owned:
                continue
            if any(subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", commit, b]).returncode == 0 for b in branches):
                continue
            subject = git(root, "log", "-1", "--format=%s", commit).strip()[:60]
            what = "머지" if len(parents) > 1 else "커밋"
            for f in owned:
                if harness_copy_same(root, harness, commit, f):
                    continue  # 판 올림 사본 맞추기(고정 판 정본과 같음)
                why = "보안 줄을 바꿨습니다" if f == OWNERS_FILE else "주인이 보안인 파일을 바꿨습니다"
                hint = "(충돌은 보안 담당이 claude/security에서 foundation/engine을 먼저 받아 풂)" if len(parents) > 1 else ""
                problems.append(f"{f}:1: 보안 브랜치 밖 {what} {commit[:7]}({subject})이 {why}(SC-REG-3){hint}")
        # 앞으로만: 기준 판에 이미 들어간 보안 커밋이 지금 보안 브랜치에 그대로 있어야 함(다시 쓰기 금지)
        tip = "origin/claude/security" if not os.environ.get("MOOKKO_SECURITY_BRANCH") and "origin/claude/security" in branches \
            else (branches[0] if branches else None)
        guarded = sorted({r.get("path", "") for r in base_rules if r.get("owner") == OWNER and not is_copy(r.get("path", ""))} - {""})
        if tip and guarded:
            for commit in git(root, "rev-list", "--no-merges", base, "--", *guarded).split():
                if subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", commit, tip]).returncode != 0:
                    subject = git(root, "log", "-1", "--format=%s", commit).strip()[:60]
                    problems.append(f"{OWNERS_FILE}:1: {base}에 들어간 보안 커밋 {commit[:7]}({subject})이 {tip}에 없습니다"
                                    f"(보안 브랜치를 다시 씀: rebase·force-push·지우기 금지, SC-REG-3 ①)")
    except GitError as e:
        return skip(str(e))
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

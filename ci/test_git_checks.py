"""git 기록을 보는 검사와 메모리 관문의 표본 시험 (tools.md: 새 검사는 잡아야 할 표본과 통과시켜야 할 표본으로 시험).

ci/fixtures/는 파일 표본이라 커밋·브랜치·머지를 담지 못한다. 그래서 임시 git 저장소를 만들어 시험한다(mookko-rust-qa 추가 6 ④).
- check-owner-paths.py(SC-REG-3): 보안 밖 커밋, cherry-pick, 충돌을 푼 머지, 깨끗한 머지, 하네스 사본 같음, owners.json 보안 줄 지움,
  보안 브랜치 없음 + MOOKKO_REQUIRE_GIT_HISTORY=1
- dev/memory-guard.py: 비상 기다림이 한 실행(MOOKKO_RUN_ID)에서 maxWaitMinutes를 한 번만 쓰는지(추가 6 ⑥)
test_ci_checks.py가 불러 같은 임시 폴더 아래에서 돌린다. 단독 실행도 된다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
OWNER_PATHS = HARNESS / "ci" / "check-owner-paths.py"
MEMORY_GUARD = HARNESS / "dev" / "memory-guard.py"
SECURITY = "docs/policy/sec.json"


def sh(repo: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", check=True, env=env).stdout


def write(repo: Path, rel: str, text: str) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text, encoding="utf-8")


def commit(repo: Path, msg: str, **files: str) -> None:
    for rel, text in files.items():
        write(repo, rel.replace("__", "/"), text)
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", msg)


def owners(*security: str) -> str:
    rules = [{"path": "docs/", "owner": "통합"}] + [{"path": p, "owner": "보안"} for p in security]
    return json.dumps({"rules": rules}, ensure_ascii=False)


def new_repo(base: Path, name: str) -> Path:
    repo = base / name
    repo.mkdir(parents=True)
    sh(repo, "init", "-q", "-b", "work")
    commit(repo, "기준", **{"docs__coordination__owners.json": owners(SECURITY, ".claude/skills/"), SECURITY.replace("/", "__"): "0\n",
                           ".claude__skills__x.md": "옛\n"})
    sh(repo, "branch", "foundation/engine")
    sh(repo, "branch", "claude/security")
    return repo


def owner_check(repo: Path, harness: Path, **env: str) -> tuple[int, list[str]]:
    full = {k: v for k, v in os.environ.items() if not k.startswith("MOOKKO_")}
    full.update(env)
    r = subprocess.run([sys.executable, "-X", "utf8", str(OWNER_PATHS), str(repo), str(harness)],
                       capture_output=True, text=True, encoding="utf-8", env=full)
    return r.returncode, [line for line in r.stdout.splitlines() if ":1: " in line]


def owner_cases(base: Path) -> list[str]:
    harness = base / "harness"
    write(harness, "skills/x.md", "새\n")
    failures: list[str] = []

    def expect(name: str, repo: Path, rc: int, count: int, **env: str) -> None:
        got_rc, lines = owner_check(repo, harness, **env)
        if got_rc != rc or len(lines) != count:
            failures.append(f"ci/test_git_checks.py:1: owner-paths {name}: rc {got_rc}·문제 {len(lines)}건(기대 rc {rc}·{count}건) {lines}")

    # 깨끗한 머지: 보안 브랜치 커밋을 머지로 받음 → 통과
    repo = new_repo(base, "clean-merge")
    sh(repo, "checkout", "-q", "claude/security")
    commit(repo, "보안", **{SECURITY.replace("/", "__"): "1\n"})
    sh(repo, "checkout", "-q", "work")
    commit(repo, "다른 일", **{"docs__a.md": "a\n"})
    sh(repo, "merge", "-q", "--no-ff", "-m", "보안 통합", "claude/security")
    expect("깨끗한 머지", repo, 0, 0)

    # 보안 밖 커밋 → 1
    repo = new_repo(base, "outside")
    commit(repo, "몰래", **{SECURITY.replace("/", "__"): "9\n"})
    expect("보안 밖 커밋", repo, 1, 1)

    # cherry-pick: 보안 커밋을 옮겨 심으면 해시가 달라 조상 아님 → 1
    repo = new_repo(base, "cherry-pick")
    sh(repo, "checkout", "-q", "claude/security")
    commit(repo, "보안", **{SECURITY.replace("/", "__"): "1\n"})
    pick = sh(repo, "rev-parse", "HEAD").strip()
    sh(repo, "checkout", "-q", "work")
    commit(repo, "다른 일", **{"docs__a.md": "a\n"})
    sh(repo, "cherry-pick", pick)
    expect("cherry-pick", repo, 1, 1)

    # 충돌을 푼 머지: 어느 부모와도 다른 내용으로 풀면 머지가 바꾼 것 → 1
    repo = new_repo(base, "conflict-merge")
    sh(repo, "checkout", "-q", "claude/security")
    commit(repo, "보안", **{SECURITY.replace("/", "__"): "1\n"})
    sh(repo, "checkout", "-q", "work")
    commit(repo, "통합 쪽", **{"docs__a.md": "a\n"})
    subprocess.run(["git", "-C", str(repo), "merge", "-q", "--no-ff", "--no-commit", "claude/security"], capture_output=True)
    write(repo, SECURITY, "2\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "보안 통합(풀며 고침)")
    expect("충돌을 푼 머지", repo, 1, 1)

    # 하네스 사본 같음: 보안 경로라도 고정 판 정본과 같으면 → 통과
    repo = new_repo(base, "copy-same")
    commit(repo, "판 올림 사본", **{".claude__skills__x.md": "새\n"})
    expect("사본 같음", repo, 0, 0)

    # owners.json 보안 줄을 지운 뒤 보안 파일을 고침 → 줄 지움 1 + 파일 1(기준 판 규칙이 남아 있음)
    repo = new_repo(base, "owners-drop")
    commit(repo, "줄 지움", **{"docs__coordination__owners.json": owners(".claude/skills/")})
    commit(repo, "몰래", **{SECURITY.replace("/", "__"): "9\n"})
    expect("보안 줄 지움", repo, 1, 2)

    # 보안 브랜치가 없고 REQUIRE=1 → 대조 못 함 실패 1
    repo = new_repo(base, "no-branch")
    sh(repo, "branch", "-D", "claude/security")
    commit(repo, "몰래", **{SECURITY.replace("/", "__"): "9\n"})
    expect("브랜치 없음·REQUIRE", repo, 1, 1, MOOKKO_REQUIRE_GIT_HISTORY="1")
    return failures


def memory_cases(base: Path) -> list[str]:
    """비상 문턱 0%(늘 비상)·resume 0%·기한 3초로 같은 실행에서 두 번 부르면, 처음만 기다리고 둘째는 바로 진행."""
    cfg = json.loads((HARNESS / "config" / "dev" / "memory-guard.json").read_text(encoding="utf-8"))
    cfg.update(emergencyPercent=0, resumePercent=0, maxWaitMinutes=0.05, pollSeconds=1, source="linux",
               runStateFile=str(base / "memory-runs.json"), dropCacheStamp=str(base / "drop-stamp"))
    settings = base / "memory-guard.json"
    settings.write_text(json.dumps(cfg), encoding="utf-8")
    env = dict(os.environ, MOOKKO_MEMORY_GUARD_SETTINGS=str(settings), MOOKKO_RUN_ID="t-1")
    failures: list[str] = []
    timings = []
    for _ in range(2):
        start = time.monotonic()
        r = subprocess.run([sys.executable, "-X", "utf8", str(MEMORY_GUARD), "step", "t", "4"],
                           capture_output=True, text=True, encoding="utf-8", env=env)
        timings.append(time.monotonic() - start)
        if r.returncode != 0 or r.stdout.strip() != "4":
            failures.append(f"ci/test_git_checks.py:1: memory-guard 비상 표본: rc {r.returncode}·출력 {r.stdout.strip()!r}(기대 0·'4') {r.stderr[-300:]}")
    if not failures and not (timings[0] >= 2.5 and timings[1] < 2.0):
        failures.append(f"ci/test_git_checks.py:1: memory-guard 실행 몫: 첫 {timings[0]:.1f}초·둘째 {timings[1]:.1f}초(기대 첫 ≥3초, 둘째 바로)")
    return failures


def run_all(base: Path) -> list[str]:
    return owner_cases(base / "owner-paths") + memory_cases(base)


def main() -> int:
    root = Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "mookko-test" / "rustdev"
    root.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="git-checks-", dir=root))
    failures = run_all(base)
    for f in failures:
        print(f)
    if failures:
        print(f"git check samples failed; kept {base}")
        return 1
    shutil.rmtree(base)
    print("git check samples passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

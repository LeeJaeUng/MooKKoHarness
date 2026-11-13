"""git 기록을 보는 검사와 메모리 관문의 표본 시험 (tools.md: 새 검사는 잡아야 할 표본과 통과시켜야 할 표본으로 시험).

ci/fixtures/는 파일 표본이라 커밋·브랜치·머지를 담지 못한다. 그래서 임시 git 저장소를 만들어 시험한다(mookko-rust-qa 추가 6 ④).
- check-owner-paths.py(SC-REG-3): 보안 밖 커밋, cherry-pick, 충돌을 푼 머지, 깨끗한 머지, 하네스 사본 같음, owners.json 보안 줄 지움,
  보안 브랜치 다시 씀(앞으로만), 사본은 커밋 내용으로 비교, 보안 브랜치 없음 + MOOKKO_REQUIRE_GIT_HISTORY=1
- dev/memory-guard.py: 비상 기다림이 한 실행(MOOKKO_RUN_ID)에서 maxWaitMinutes를 한 번만 쓰는지(추가 6 ⑥)
- dev/build-slot-watch.py: 죽은 감싸개의 시험 컨테이너가 쥔 잠금은 그 컨테이너만 멈춤, 진행 기록이 오래된 실행은 경보만(PM 11-04)
- ci/check-harness-lock.py: harness.lock 판 올림에 카나리 영수증(PM 11-04 ①, rust-qa 추가 8 ②)
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


def clean_env(**extra: str) -> dict[str, str]:
    """git·MOOKKO_ 환경 변수를 뺀 환경. check-all은 Windows worktree에서 GIT_DIR·GIT_WORK_TREE를 내보내므로, 그대로 물려받으면
    표본 저장소가 아니라 제품 저장소에 git init·add가 닿는다(2026-11-04 11차 check-all에서 제품 .git/config에 core.worktree가 써짐).
    전역·시스템 git 설정도 읽지 않는다(서명·훅 설정이 표본을 흔들지 않게)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "MOOKKO_"))}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t", **extra)
    return env


def sh(repo: Path, *args: str) -> str:
    env = clean_env()
    if not repo.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()) and "mookko-test" not in repo.parts:
        raise RuntimeError(f"표본 git 저장소는 임시 폴더 아래여야 합니다: {repo}")
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
    full = clean_env(**env)
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
    subprocess.run(["git", "-C", str(repo), "merge", "-q", "--no-ff", "--no-commit", "claude/security"], capture_output=True, env=clean_env())
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

    # 앞으로만: 기준 판에 들어간 보안 커밋을 보안 브랜치에서 지워 다시 씀 → 1
    repo = new_repo(base, "rewritten")
    first = sh(repo, "rev-parse", "HEAD").strip()
    sh(repo, "checkout", "-q", "claude/security")
    commit(repo, "보안", **{SECURITY.replace("/", "__"): "1\n"})
    sh(repo, "checkout", "-q", "work")
    sh(repo, "merge", "-q", "--no-ff", "-m", "보안 통합", "claude/security")
    sh(repo, "branch", "-f", "foundation/engine", "work")
    sh(repo, "checkout", "-q", "claude/security")
    sh(repo, "reset", "-q", "--hard", first)
    commit(repo, "보안 다시 씀", **{SECURITY.replace("/", "__"): "3\n"})
    sh(repo, "checkout", "-q", "work")
    expect("보안 브랜치 다시 씀", repo, 1, 1)

    # 사본 같음은 커밋 내용으로: 커밋 뒤 작업 트리만 정본과 같게 바꿔도 통과하지 않음 → 1
    repo = new_repo(base, "copy-worktree")
    commit(repo, "사본 다름", **{".claude__skills__x.md": "다름\n"})
    write(repo, ".claude/skills/x.md", "새\n")
    expect("사본은 커밋 내용", repo, 1, 1)

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
    env = clean_env(MOOKKO_MEMORY_GUARD_SETTINGS=str(settings), MOOKKO_RUN_ID="t-1")
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


def slot_cases(base: Path) -> list[str]:
    """빌드 자리 감시(PM 11-04): ① 감싸개가 죽은 시험 컨테이너(conmon)가 쥔 잠금 → 그 컨테이너만 멈춤(가짜 podman이 받음)
    ② 실행 입구가 쥐었는데 진행 기록이 오래됨 → 경보만, 멈추지 않음 ③ 살아 있음은 새것인데 단계 진행 기록이 오래됨(교착) → 경보·경보 파일
    ④ conmon 없이 rootlessport만 잠금을 쥠 → 경보만. 가짜 프로세스는 이름이 conmon·check-all.sh·rootlessport인 셸 스크립트."""
    import shutil as _sh
    import signal as _sig
    watch = HARNESS / "dev" / "build-slot-watch.py"
    failures: list[str] = []
    slots = base / "slots"
    slots.mkdir(parents=True)
    settings = base / "build-slots.json"
    settings.write_text(json.dumps({"count": 1, "dir": str(slots), "stallMinutes": 15}), encoding="utf-8")
    stopped = base / "podman-args"
    fake_podman = base / "podman"
    fake_podman.write_text(f"#!/bin/sh\necho \"$@\" >> {stopped}\nkill $(cat {base}/holder.pid)\n", encoding="utf-8")
    fake_podman.chmod(0o755)
    env = clean_env(MOOKKO_BUILD_SLOTS_SETTINGS=str(settings), MOOKKO_PODMAN=str(fake_podman))

    def hold(name: str, *args: str) -> subprocess.Popen:
        script = base / name
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(f"#!/bin/bash\nexec 9>{slots}/slot-1\nflock 9\necho $$ > {base}/holder.pid\nsleep 300 9>&-\n", encoding="utf-8")
        script.chmod(0o755)
        proc = subprocess.Popen([str(script), *args], env=env, start_new_session=True)
        for _ in range(50):
            if (base / "holder.pid").exists():
                break
            time.sleep(0.1)
        return proc

    # ① 죽은 감싸개(pid 999999)의 시험 컨테이너 이름을 단 conmon이 쥠 → podman stop <id>
    proc = hold("conmon", "-c", "abc123", "-n", "mookko-test-pg-20261104133308-999999")
    time.sleep(0.3)
    r = subprocess.run([sys.executable, "-X", "utf8", str(watch), "check"], capture_output=True, text=True, encoding="utf-8", env=env)
    proc.wait(timeout=10)
    try:
        os.killpg(proc.pid, _sig.SIGTERM)  # 남은 sleep(잠금 fd는 닫음)까지
    except ProcessLookupError:
        pass
    args = stopped.read_text(encoding="utf-8").strip() if stopped.exists() else ""
    if args != "stop -t 10 abc123" or "멈춤" not in r.stderr:
        failures.append(f"ci/test_git_checks.py:1: 자리 감시 주인 없는 잠금: podman 인자 {args!r}, 경보 {r.stderr.strip()[:200]!r}")
    (base / "holder.pid").unlink()

    # ② 실행 입구(check-all.sh)가 쥐고 진행 기록이 20분 전 → 경보만, podman 안 부름
    stopped.unlink(missing_ok=True)
    proc = hold("ci/check-all.sh")
    beat = slots / "heartbeat-1"
    beat.touch()
    old = time.time() - 20 * 60
    os.utime(beat, (old, old))
    time.sleep(0.3)
    r = subprocess.run([sys.executable, "-X", "utf8", str(watch), "check"], capture_output=True, text=True, encoding="utf-8", env=env)
    alive = proc.poll() is None
    try:
        os.killpg(proc.pid, _sig.SIGTERM)
    except ProcessLookupError:
        pass
    proc.wait(timeout=10)
    if not alive or stopped.exists() or "진행 기록 없이" not in r.stderr:
        failures.append(f"ci/test_git_checks.py:1: 자리 감시 진행 멈춤: 살아 있음 {alive}, podman 부름 {stopped.exists()}, 경보 {r.stderr.strip()[:200]!r}")
    (base / "holder.pid").unlink(missing_ok=True)

    # ③ 교착(rust-qa 11-13 ①): 살아 있음 표시는 방금 고쳤는데 단계 진행 기록이 70분 전 → 경보, 경보 파일(MOOKKO_SLOT_ALERT_FILE)에도 남음
    alerts = base / "product-data" / "build-slot-alerts.log"
    env["MOOKKO_SLOT_ALERT_FILE"] = str(alerts)
    (slots / "watch-state.json").unlink(missing_ok=True)
    proc = hold("ci/check-all.sh")
    beat.touch()
    progress = slots / "progress-1"
    progress.touch()
    old = time.time() - 70 * 60
    os.utime(progress, (old, old))
    time.sleep(0.3)
    r = subprocess.run([sys.executable, "-X", "utf8", str(watch), "check"], capture_output=True, text=True, encoding="utf-8", env=env)
    try:
        os.killpg(proc.pid, _sig.SIGTERM)
    except ProcessLookupError:
        pass
    proc.wait(timeout=10)
    written = alerts.read_text(encoding="utf-8") if alerts.exists() else ""
    if "단계 진행 기록 없이" not in r.stderr or "단계 진행 기록 없이" not in written or "cwd=" not in written:
        failures.append(f"ci/test_git_checks.py:1: 자리 감시 교착: 경보 {r.stderr.strip()[:200]!r}, 경보 파일 {written[:200]!r}")
    (base / "holder.pid").unlink(missing_ok=True)

    # ④ conmon 없이 rootlessport만 잠금을 쥠(rust-qa 11-13 ②) → 멈추지 않고 경보
    (slots / "watch-state.json").unlink(missing_ok=True)
    stopped.unlink(missing_ok=True)
    progress.unlink(missing_ok=True)
    proc = hold("rootlessport")
    time.sleep(0.3)
    r = subprocess.run([sys.executable, "-X", "utf8", str(watch), "check"], capture_output=True, text=True, encoding="utf-8", env=env)
    alive = proc.poll() is None
    try:
        os.killpg(proc.pid, _sig.SIGTERM)
    except ProcessLookupError:
        pass
    proc.wait(timeout=10)
    if not alive or stopped.exists() or "실행 입구 없이 잠금을 쥔 프로세스" not in r.stderr or "rootlessport" not in r.stderr:
        failures.append(f"ci/test_git_checks.py:1: 자리 감시 rootlessport만 남음: 살아 있음 {alive}, podman 부름 {stopped.exists()}, 경보 {r.stderr.strip()[:200]!r}")
    _sh.rmtree(slots, ignore_errors=False)
    return failures


def lock_cases(base: Path) -> list[str]:
    """check-harness-lock(카나리 영수증): 판 그대로 통과, 올렸는데 영수증 없음·다른 판 영수증 실패, 맞는 영수증 통과,
    MOOKKO_CANARY_RUN은 카나리 사본 폴더 밖에서 실패."""
    check = HARNESS / "ci" / "check-harness-lock.py"
    failures: list[str] = []
    old, new = "a" * 40, "b" * 40
    head = "repo = MooKKoHarness\ncommit = {}\n"
    receipt = f"canary = {new} base={'c' * 40} at=2026-11-10T01:02:03Z result=pass\n"

    def case(name: str, lock: str, rc: int, **env: str) -> None:
        repo = base / name
        repo.mkdir(parents=True)
        sh(repo, "init", "-q", "-b", "work")
        commit(repo, "기준", **{"harness.lock": head.format(old)})
        sh(repo, "branch", "foundation/engine")
        commit(repo, "판 올림", **{"harness.lock": lock})
        r = subprocess.run([sys.executable, "-X", "utf8", str(check), str(repo)], capture_output=True, text=True, encoding="utf-8",
                           env=clean_env(MOOKKO_REQUIRE_GIT_HISTORY="1", **env))
        if r.returncode != rc:
            failures.append(f"ci/test_git_checks.py:1: harness-lock {name}: rc {r.returncode}(기대 {rc}) {r.stdout.strip()[:200]}")

    case("same", head.format(old) + "# 설명만 바꿈\n", 0)
    case("no-receipt", head.format(new), 1)
    case("other-receipt", head.format(new) + receipt.replace(new, "d" * 40, 1), 1)
    case("receipt", head.format(new) + receipt, 0)
    case("canary-env-outside", head.format(new), 1, MOOKKO_CANARY_RUN="1")
    return failures


def canary_config_cases(base: Path) -> list[str]:
    """카나리 공용 .git/config 지문(config_view): branch.<이름>.* 추가는 같게, core.worktree·remote.origin.url 변경은 다르게(rust-qa 11-13)."""
    failures: list[str] = []
    script = (HARNESS / "dev" / "harness-canary.sh").read_text(encoding="utf-8")
    start = script.index("config_view() {")
    func = script[start:script.index("\n}\n", start) + 3]
    repo = base / "repo"
    repo.mkdir(parents=True)
    sh(repo, "init", "-q", "-b", "work")
    sh(repo, "remote", "add", "origin", "https://example.invalid/a.git")
    config = repo / ".git" / "config"

    def view() -> str:
        r = subprocess.run(["bash", "-c", func + '\nconfig_view "$1"', "x", str(config)], capture_output=True, text=True,
                           encoding="utf-8", env=clean_env(), cwd=repo)
        if r.returncode != 0:
            failures.append(f"ci/test_git_checks.py:1: config_view rc {r.returncode}: {r.stderr.strip()[:200]}")
        return r.stdout

    def setc(key: str, value: str) -> None:
        # 파일로 바로 씀(core.worktree를 바꾼 뒤에는 그 저장소에서 git이 돌지 않을 수 있음)
        # 지금 폴더(check-all은 Windows gitdir을 가리키는 worktree)에서 저장소를 찾지 않게 / 에서 부름(11-13 check-all에서 실패)
        subprocess.run(["git", "config", "--file", str(config), key, value], check=True, env=clean_env(), cwd="/")

    before = view()
    setc("branch.x.remote", "origin")
    setc("branch.x.merge", "refs/heads/x")
    if view() != before:
        failures.append("ci/test_git_checks.py:1: 카나리 지문: branch.x.* 추가가 지문을 바꿈(통과해야 함)")
    for key, value in (("core.worktree", "/mnt/elsewhere"), ("remote.origin.url", "https://example.invalid/b.git")):
        saved = view()
        setc(key, value)
        if view() == saved:
            failures.append(f"ci/test_git_checks.py:1: 카나리 지문: {key} 변경을 못 잡음(실패해야 함)")
    return failures


def checker_changed_cases(base: Path) -> list[str]:
    """--init-baseline --checker-changed=<하네스 커밋>:<사유>(rust-qa 11-13 보통 1): 검사 파일을 바꾼 새 하네스 커밋만 받음.
    통과: 기준 판 lock 뒤에 check-hardcoded-values.py를 바꾼 커밋. 실패: 검사 파일을 안 바꾼 커밋, 기준 판 lock에 이미 든 커밋,
    모양 틀림(사유만), 하네스 저장소 없음."""
    failures: list[str] = []
    check = HARNESS / "ci" / "check-hardcoded-values.py"
    harness = base / "harness"
    harness.mkdir(parents=True)
    sh(harness, "init", "-q", "-b", "main")
    commit(harness, "검사 처음", **{"ci/check-hardcoded-values.py": "# v1\n"})
    old_commit = sh(harness, "rev-parse", "HEAD").strip()
    commit(harness, "검사 바꿈", **{"ci/check-hardcoded-values.py": "# v2\n"})
    changed = sh(harness, "rev-parse", "HEAD").strip()
    commit(harness, "다른 파일", **{"README.md": "x\n"})
    other = sh(harness, "rev-parse", "HEAD").strip()
    policy = {"enforce": False, "expires": "2099-01-01", "baseline": {"crates/x/src/lib.rs": {"NUM": 1}}}

    def case(name: str, value: str | None, rc: int, with_repo: bool = True) -> None:
        repo = base / name
        repo.mkdir(parents=True)
        sh(repo, "init", "-q", "-b", "work")
        commit(repo, "기준", **{"harness.lock": f"commit = {old_commit}\n",
                               "docs/policy/hardcoded-values.json": json.dumps(policy) + "\n"})
        sh(repo, "branch", "foundation/engine")
        args = [sys.executable, "-X", "utf8", str(check), str(repo), "--init-baseline"]
        if value is not None:
            args.append(f"--checker-changed={value}")
        extra = {"MOOKKO_HARNESS_REPO": str(harness)} if with_repo else {}
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", env=clean_env(**extra), cwd=repo)
        if r.returncode != rc:
            failures.append(f"ci/test_git_checks.py:1: checker-changed {name}: rc {r.returncode}(기대 {rc}) {r.stdout.strip()[:200]}")

    case("changed", f"{changed}:검사 넓힘", 0)
    case("no-checker-change", f"{other}:검사 안 바뀜", 1)
    case("already-in-base", f"{old_commit}:옛 판", 1)
    case("reason-only", "사유만", 1)
    case("no-flag", None, 1)
    case("no-harness-repo", f"{changed}:검사 넓힘", 1, with_repo=False)
    return failures


def ratchet_base_cases(base: Path) -> list[str]:
    """래칫 기준 판 대조(백로그 9d): git 최상위인데 기준 판(foundation/engine)이 없으면 MOOKKO_REQUIRE_GIT_HISTORY=1에서 실패,
    그 변수가 없으면 통과(건너뜀 표시), 기준 판이 있고 기준을 늘리지 않았으면 통과, 사유 없이 늘렸으면 실패."""
    failures: list[str] = []
    check = HARNESS / "ci" / "check-hardcoded-values.py"
    policy = {"enforce": False, "expires": "2099-01-01", "baseline": {}}

    def case(name: str, branch: bool, raise_after: bool, rc: int, raised_value: object = None, **env: str) -> None:
        repo = base / name
        repo.mkdir(parents=True)
        sh(repo, "init", "-q", "-b", "work")
        commit(repo, "기준", **{"docs/policy/hardcoded-values.json": json.dumps(policy) + "\n"})
        if branch:
            sh(repo, "branch", "foundation/engine")
        if raise_after:
            raised = dict(policy, baseline={"crates/x/src/lib.rs": {"NUM": 3}})
            if raised_value is not None:
                raised["raised"] = {"crates/x/src/lib.rs": raised_value}
            write(repo, "docs/policy/hardcoded-values.json", json.dumps(raised) + "\n")
        r = subprocess.run([sys.executable, "-X", "utf8", str(check), str(repo)], capture_output=True, text=True, encoding="utf-8",
                           env=clean_env(**env), cwd=repo)
        if r.returncode != rc:
            failures.append(f"ci/test_git_checks.py:1: ratchet-base {name}: rc {r.returncode}(기대 {rc}) {r.stdout.strip()[-200:]}")

    case("no-base-required", False, False, 1, MOOKKO_REQUIRE_GIT_HISTORY="1")
    case("no-base-optional", False, False, 0)
    case("base-same", True, False, 0, MOOKKO_REQUIRE_GIT_HISTORY="1")
    case("base-raised", True, True, 1, MOOKKO_REQUIRE_GIT_HISTORY="1")
    # raised 모양(rust-qa 11-14 15번, 9v): 글 하나는 실패, {owner, expires, reason}은 통과, 기한 지남은 실패
    case("raised-string", True, True, 1, "사유 글만", MOOKKO_REQUIRE_GIT_HISTORY="1")
    case("raised-owner", True, True, 0, {"owner": "로그", "expires": "2099-01-01", "reason": "새 코드, 다음 묶음에 옮김"},
         MOOKKO_REQUIRE_GIT_HISTORY="1")
    case("raised-expired", True, True, 1, {"owner": "로그", "expires": "2020-01-01", "reason": "지남"}, MOOKKO_REQUIRE_GIT_HISTORY="1")
    return failures


def acceptance_fresh_cases(base: Path) -> list[str]:
    """인수 기록 신선도(CA-9): 통과 기록 뒤 서비스 경로가 바뀌면 경고(--l4·enforce면 실패), 다른 경로만 바뀌면 경고 없음."""
    failures: list[str] = []
    check = HARNESS / "ci" / "check-acceptance.py"
    plan = {"services": [{"id": "links", "owner": "links", "due": "2026-11-10", "enforce": True}]}

    def setup(name: str, later: dict[str, str]) -> Path:
        repo = base / name
        repo.mkdir(parents=True)
        sh(repo, "init", "-q", "-b", "work")
        commit(repo, "처음", **{"acceptance/services.json": json.dumps(plan) + "\n", "crates/services/links/src/lib.rs": "// 1\n"})
        head = sh(repo, "rev-parse", "HEAD").strip()
        record = {"service": "links", "commit": head, "command": "x", "startedAt": "2026-11-13T00:00:00Z", "passed": 9, "failed": 0,
                  "skipped": 0, "engine": "t"}
        commit(repo, "기록", **{f"acceptance/runs/links/20261113T0000Z-{head[:7]}.json": json.dumps(record) + "\n"})
        if later:
            commit(repo, "나중", **later)
        return repo

    def run(repo: Path, *flags: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-X", "utf8", str(check), str(repo), *flags], capture_output=True, text=True,
                              encoding="utf-8", env=clean_env(), cwd=repo)

    stale = setup("stale", {"crates/services/links/src/lib.rs": "// 2\n"})
    r = run(stale)
    if r.returncode != 0 or "CA-9" not in r.stdout:
        failures.append(f"ci/test_git_checks.py:1: acceptance 신선도 경고 없음: rc {r.returncode} {r.stdout.strip()[-200:]}")
    r = run(stale, "--l4")
    if r.returncode != 1:
        failures.append(f"ci/test_git_checks.py:1: acceptance 신선도 --l4 enforce 실패 아님: rc {r.returncode} {r.stdout.strip()[-200:]}")
    fresh = setup("fresh", {"crates/services/other/src/lib.rs": "// 2\n"})
    r = run(fresh, "--l4")
    if r.returncode != 0 or "CA-9" in r.stdout:
        failures.append(f"ci/test_git_checks.py:1: acceptance 다른 경로 변경에 신선도 지적: rc {r.returncode} {r.stdout.strip()[-200:]}")
    return failures


def run_all(base: Path) -> list[str]:
    return (owner_cases(base / "owner-paths") + memory_cases(base) + slot_cases(base / "slot-watch") + lock_cases(base / "harness-lock")
            + canary_config_cases(base / "canary-config") + checker_changed_cases(base / "checker-changed")
            + ratchet_base_cases(base / "ratchet-base") + acceptance_fresh_cases(base / "acceptance-fresh"))


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

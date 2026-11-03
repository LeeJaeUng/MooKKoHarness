"""하네스 검사 스크립트의 표본 시험 (tools.md: 새 검사는 잡아야 할 표본과 통과시켜야 할 표본으로 시험).

scripts/ci/fixtures/<검사>/{good,bad}/ 아래 표본을 임시 저장소로 복사해 검사를 돌린다. 표본 파일은 이름 끝에 `.txt`를
붙여 두어(예: a.sh.txt) 저장소 자체 검사가 표본을 실제 파일로 읽지 않게 하고, 복사할 때 `.txt`를 뗀다.
- good: 종료 코드 0
- bad: 종료 코드 1이고 문제 줄 수가 EXPECTED_BAD와 같음(검사가 잡는 개수가 줄면 실패)
임시 폴더는 $TMPDIR/mookko-test/rustdev/<실행>/에 만들고, 이 시험이 성공하면 지우고 실패하면 남긴다.
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts" / "ci" / "fixtures"
CHECKS = {
    "dev-exposure": ROOT / "scripts" / "ci" / "check-dev-exposure.py",
    "acceptance": ROOT / "scripts" / "ci" / "check-acceptance.py",
    "file-size": ROOT / "scripts" / "ci" / "check-file-size.py",
    "engine-reuse": ROOT / "scripts" / "ci" / "check-engine-reuse.py",
    "endpoints": ROOT / "scripts" / "ci" / "check-no-hardcoded-endpoints.py",
    "lint-escapes": ROOT / "scripts" / "ci" / "check-lint-escapes.py",
    "waivers": ROOT / "scripts" / "ci" / "check-waivers.py",
    "tempdirs": ROOT / "scripts" / "ci" / "check-test-tempdirs.py",
    "boundaries": ROOT / "scripts" / "ci" / "check-boundaries.py",
    "stack": ROOT / "scripts" / "ci" / "check-stack.py",
    "forbid-unsafe": ROOT / "scripts" / "ci" / "check-forbid-unsafe.py",
    "systemd-units": ROOT / "scripts" / "ci" / "check-systemd-units.py",
    "containers": ROOT / "scripts" / "ci" / "check-containers.py",
    "design-sources": ROOT / "scripts" / "ci" / "check-design-sources.py",
    "hardcoded": ROOT / "scripts" / "ci" / "check-hardcoded-values.py",
}
# cargo metadata로 판정하는 검사는 같은 작은 작업 공간 표본(cargo-ws)을 함께 쓴다. 복사한 뒤 cargo generate-lockfile --offline.
FIXTURE_DIR = {"boundaries": "cargo-ws", "stack": "cargo-ws", "forbid-unsafe": "cargo-ws"}
# cargo-ws bad:
#   boundaries: service s → adapter a1 1, adapter a1 → adapter a2 2(층 허용·어댑터끼리), crates/ 밖 tools/x 1,
#     인수 시험 acceptance/bad → service s 1(엔진만 허용). good: acceptance/ok → engine e.
#   stack: service s → `hyper` 1, 이름에 rust(패키지 rusty-svc·대상 rusty_svc) 2, web vue 1, yarn.lock 1, pnpm-lock 없음 1.
#   forbid-unsafe: tools/x lib 1, s의 tests/t.rs 1.
# containers bad: Dockerfile 5(다이제스트 없음·latest·비밀 ENV·원격 ADD·USER root), compose 14(필수 칸 없음 5, 다이제스트 없는 image, privileged, host 네트워크, seccomp unconfined, docker.sock, cap_add, user root, 주소 없는 포트, 0.0.0.0 포트).
#   Kubernetes 25(멀티 AZ 3: zone 분산 없음·replicas 2·HPA minReplicas 없음, Namespace 라벨 없음·기본 차단 없음 2, Deployment 필수 칸 6, 금지 6(hostNetwork·runAsUser 0·Unconfined·add·secretKeyRef·hostPath),
#   컨테이너 5(다이제스트·limits cpu·memory·probe 둘), Service NodePort 1, StorageClass Delete 1, PV Retain 없음 1).
#   good: 한 줄 맵 resources, 운영툴 배포기 주석 예외, Job은 probe 없어도 됨.
# design-sources bad(enforce true): 결정 표에 표준 출처 칸 없음 1, 빈 칸 1, "-" 1. good: 출처·해당 없음, 결정 아닌 표는 안 봄.
# hardcoded bad(enforce true): DUR 1, NUM 2(비교식·호출 인자), INC 1(엔진 시험이 서비스 파일), PATH 3(드라이브 문자 경로·/mnt 드라이브·/home 사용자), 기준보다 줄어듦 1.
#   good: const 안 Duration·숫자, 문자열(여러 줄 포함)·문자·99, 시험 모듈, 기준 안 개수, crate 안 include, 상대 경로.
# systemd-units bad: User=root 1, NoNewPrivileges 없음 1, ExecStart=+ 1, .socket 1. good은 mookko-links-maintain.service 사본.
# lint-escapes bad: src #[allow] 1, #![allow] 1, cfg_attr(…allow) 1, tests의 정해진 머리줄이 아닌 allow 1, web eslint-disable 1,
#   acceptance/ 아래 #[allow] 1.
#   good: tests 머리줄, 등록부에 오른 예외.
# tempdirs bad: join이 mookko-test 아님 1, temp_dir 단독 1, panicking 없는 Drop 1, mookko-test 밖 변수 1, "$HOME/target" 1, /tmp/* 1, 정의 없는 변수 1.
# waivers bad: 빠진 칸 1, id 겹침 1, 만료 1, 180일 넘음 1, 없는 경로 1, adr 문서 없음 1. 날짜는 @@TODAY±N@@로 실행 날 기준.
# acceptance bad: enforce인데 기록 없음 1, 깨진 JSON 1, 다른 service 1, 짧은 commit 1, passed 형 틀림 1, 파일 이름 틀림 1,
#   services.json에 없는 runs 폴더 1, enforce 서비스의 가장 최근 기록이 실패(앞 기록은 통과) 1.
# file-size bad: src 601줄 1, 시험 모듈 뒤 코드까지 650줄 1, 600줄 이하인데 예외가 남음 1, 예외의 파일이 없음 1(tests/ 900줄은 세지 않음).
#   good: `#[cfg(test)] mod t;`가 가리키는 900줄 t.rs는 세지 않음, src/tests/ 모듈 폴더는 셈.
# engine-reuse bad: C1 상수 1, C2 SystemClock 1, C3 is_identifier 1, C4 prev_hash 1, 복사본이 없는데 남은 예외 1,
#   넓힌 모양 4(SystemTime::now, "recent_mfa_required", Hmac<, fn rw() -> TxOptions).
# endpoints bad: IPv4 1, localhost 1, URL 1, host:port 1, Ipv4Addr::LOCALHOST 2(생성자·localhost).
#   good: 판 문자열 "1.2.3.4.5"·"v1.0.0.1", 300으로 시작하는 넷 덩어리, 주석 줄은 잡지 않음.
EXPECTED_BAD = {
    "dev-exposure": 15,
    "acceptance": 8,
    "file-size": 4,
    "engine-reuse": 9,
    "endpoints": 6,
    "lint-escapes": 6,
    "waivers": 6,
    "tempdirs": 7,
    "boundaries": 5,
    "stack": 6,
    "forbid-unsafe": 2,
    "systemd-units": 4,
    "containers": 44,
    "design-sources": 3,
    "hardcoded": 8,
}
PROBLEM_LINE = re.compile(r"^(?:\s*-\s+)?\S+:\d+: ")
# 줄 번호 없이 `  - …`로 문제를 내는 검사
_DASH = re.compile(r"^\s+-\s+\S")
PROBLEM_LINE_BY_CHECK = {k: _DASH for k in ("waivers", "boundaries", "stack", "forbid-unsafe", "systemd-units")}
DATE_TOKEN = re.compile(r"@@TODAY([+-]\d+)@@")


def materialize(src: Path, dest: Path) -> None:
    """`.txt`를 떼어 복사하고, 글 안의 @@TODAY±N@@을 실행 날 기준 날짜로 바꾼다(기한 표본이 날짜가 지나며 썩지 않게)."""
    today = datetime.date.today()
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        name = rel.name[:-4] if rel.name.endswith(".txt") else rel.name
        target = dest / rel.parent / name
        target.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text(encoding="utf-8")
        text = DATE_TOKEN.sub(lambda m: (today + datetime.timedelta(days=int(m.group(1)))).isoformat(), text)
        target.write_text(text, encoding="utf-8")


def run(name: str, check: Path, repo: Path) -> tuple[int, list[str]]:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(check), str(repo)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    pattern = PROBLEM_LINE_BY_CHECK.get(name, PROBLEM_LINE)
    lines = [line for line in result.stdout.splitlines() if pattern.match(line)]
    return result.returncode, lines


def main() -> int:
    base = Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "mookko-test" / "rustdev"
    base.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="ci-checks-", dir=base))
    failures: list[str] = []
    for name, check in CHECKS.items():
        for kind in ("good", "bad"):
            repo = run_dir / name / kind
            materialize(FIXTURES / FIXTURE_DIR.get(name, name) / kind, repo)
            if (repo / "Cargo.toml").exists():
                # 길 의존만 있는 작은 작업 공간이라 인터넷 없이 lock을 만든다(검사가 --locked로 돈다).
                subprocess.run(["cargo", "generate-lockfile", "--offline", "--quiet"], cwd=repo, check=True)
            code, lines = run(name, check, repo)
            if kind == "good" and code != 0:
                failures.append(f"scripts/ci/fixtures/{name}/good:1: 통과해야 할 표본이 걸림(rc={code}): {lines}")
            if kind == "bad" and (code != 1 or len(lines) != EXPECTED_BAD[name]):
                failures.append(
                    f"scripts/ci/fixtures/{name}/bad:1: 잡아야 할 표본 {EXPECTED_BAD[name]}건 중 {len(lines)}건(rc={code})"
                    + "".join(f"\n  {line}" for line in lines)
                )
    for failure in failures:
        print(failure)
    if failures:
        print(f"ci check samples failed; kept {run_dir}")
        return 1
    shutil.rmtree(run_dir)
    print(f"ci check samples passed ({len(CHECKS)} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

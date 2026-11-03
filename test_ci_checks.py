"""하네스 검사 스크립트의 표본 시험 (tools.md: 새 검사는 잡아야 할 표본과 통과시켜야 할 표본으로 시험).

scripts/ci/fixtures/<검사>/{good,bad}/ 아래 표본을 임시 저장소로 복사해 검사를 돌린다. 표본 파일은 이름 끝에 `.txt`를
붙여 두어(예: a.sh.txt) 저장소 자체 검사가 표본을 실제 파일로 읽지 않게 하고, 복사할 때 `.txt`를 뗀다.
- good: 종료 코드 0
- bad: 종료 코드 1이고 문제 줄 수가 EXPECTED_BAD와 같음(검사가 잡는 개수가 줄면 실패)
임시 폴더는 $TMPDIR/mookko-test/rustdev/<실행>/에 만들고, 이 시험이 성공하면 지우고 실패하면 남긴다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts" / "ci" / "fixtures"
CHECKS = {
    "dev-exposure": ROOT / "scripts" / "ci" / "check-dev-exposure.py",
}
EXPECTED_BAD = {
    "dev-exposure": 15,
}


def materialize(src: Path, dest: Path) -> None:
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        name = rel.name[:-4] if rel.name.endswith(".txt") else rel.name
        target = dest / rel.parent / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def run(check: Path, repo: Path) -> tuple[int, list[str]]:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(check), str(repo)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    lines = [line for line in result.stdout.splitlines() if ":" in line and not line.startswith("dev exposure check")]
    return result.returncode, lines


def main() -> int:
    base = Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "mookko-test" / "rustdev"
    base.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="ci-checks-", dir=base))
    failures: list[str] = []
    for name, check in CHECKS.items():
        for kind in ("good", "bad"):
            repo = run_dir / name / kind
            materialize(FIXTURES / name / kind, repo)
            code, lines = run(check, repo)
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

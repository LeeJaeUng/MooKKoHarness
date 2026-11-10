"""harness.lock 판 올림은 카나리를 통과한 판만 (PM 지시 2026-11-04 ①, mookko-rust-qa 11-04 추가 8 ①②).

제품 harness.lock의 commit이 기준 판(MOOKKO_REGISTER_BASE, 기본 foundation/engine)의 harness.lock과 다르면, 같은 파일에
dev/harness-canary.sh가 낸 영수증 줄 `canary = <그 commit> base=<40자> at=<UTC 시각> result=pass`가 있어야 한다. 없거나 다른 판의
영수증이면 실패. 판이 그대로면 영수증을 보지 않는다. 영수증이 진짜 카나리 결과인지는 글로 알 수 없으므로 QA(rust-qa)가 카나리 기록과 대조한다.
- 카나리 실행 자체(사본에서 lock을 바꾼 채 check-all)는 MOOKKO_CANARY_RUN=1이고 제품 루트가 카나리 사본 폴더
  (<TMPDIR>/mookko-test/harness-canary/) 아래일 때만 건너뛴다. 공용 체크아웃에서 이 변수로 끌 수 없다.
- 검사 폴더가 git 최상위가 아니면(표본) 보지 않는다. git·기준 판을 읽지 못하면 "건너뜀", MOOKKO_REQUIRE_GIT_HISTORY=1이면 실패.
실패는 `harness.lock:1: 이유`.

사용: python3 -X utf8 ci/check-harness-lock.py [제품 루트]
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

COMMIT = re.compile(r"^commit\s*=\s*([0-9a-f]{40})\s*$", re.M)
RECEIPT = re.compile(r"^canary\s*=\s*([0-9a-f]{40})\s+base=([0-9a-f]{40})\s+at=(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+result=(\w+)\s*$", re.M)


def git(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")
    return result.stdout if result.returncode == 0 else None


def main(argv: list[str]) -> int:
    root = Path(argv[0]).resolve() if argv else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    required = os.environ.get("MOOKKO_REQUIRE_GIT_HISTORY") == "1"

    def skip(why: str) -> int:
        if required:
            print(f"harness.lock:1: 카나리 영수증을 대조하지 못했습니다({why})")
            print("harness lock check failed (1 problems)")
            return 1
        print(f"harness lock check skipped(통과 아님): {why}")
        return 0

    canary_root = (Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "mookko-test" / "harness-canary").resolve()
    if os.environ.get("MOOKKO_CANARY_RUN") == "1":
        if root.is_relative_to(canary_root):
            print("harness lock check passed (카나리 실행 사본)")
            return 0
        print(f"harness.lock:1: MOOKKO_CANARY_RUN은 카나리 사본({canary_root}) 안에서만 씁니다")
        return 1
    top = git(root, "rev-parse", "--show-toplevel")
    if top is None:
        return skip("git을 읽지 못함")
    if Path(top.strip()).resolve() != root:
        print("harness lock check passed (표본, git 최상위 아님)")
        return 0
    try:
        text = (root / "harness.lock").read_text(encoding="utf-8")
    except OSError as e:
        print(f"harness.lock:1: 읽지 못했습니다: {e}")
        return 1
    m = COMMIT.search(text)
    if not m:
        print("harness.lock:1: commit(40자 해시) 줄이 없습니다")
        return 1
    current = m.group(1)
    base = os.environ.get("MOOKKO_REGISTER_BASE") or "foundation/engine"
    base_text = git(root, "show", f"{base}:harness.lock")
    if base_text is None:
        return skip(f"기준 판 {base}의 harness.lock을 읽지 못함")
    bm = COMMIT.search(base_text)
    if bm and bm.group(1) == current:
        print(f"harness lock check passed (판 그대로 {current[:7]})")
        return 0
    receipts = RECEIPT.findall(text)
    good = [r for r in receipts if r[0] == current and r[3] == "pass"]
    if not good:
        have = ", ".join(f"{r[0][:7]} {r[3]}" for r in receipts) or "없음"
        print(f"harness.lock:1: 판을 {bm.group(1)[:7] if bm else '?'} → {current[:7]}로 올렸는데 그 판의 카나리 영수증이 없습니다(있는 것: {have}). "
              f"dev/harness-canary.sh로 카나리를 통과한 뒤 낸 `canary = …` 줄을 붙이세요")
        print("harness lock check failed (1 problems)")
        return 1
    print(f"harness lock check passed (판 올림 {current[:7]}, 카나리 {good[-1][2]})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

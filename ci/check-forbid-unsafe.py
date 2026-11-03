"""모든 crate 대상 루트에 `#![forbid(unsafe_code)]`가 있는지 검사 (RUST-01).

cargo metadata의 모든 대상(lib·bin·test·bench·example·build script)의 루트 파일을 본다.
공식 CI(하네스 MooKKoDev)도 같은 검사를 한다. 이 스크립트는 커밋 전 로컬 확인용이다.
"""

from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()  # 인자를 주면 표본 폴더를 검사
MARK = "#![forbid(unsafe_code)]"


def main() -> int:
    out = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--no-deps", "--locked"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    missing: list[str] = []
    count = 0
    for pkg in json.loads(out)["packages"]:
        for target in pkg["targets"]:
            count += 1
            src = Path(target["src_path"])
            if MARK not in src.read_text(encoding="utf-8"):
                missing.append(f"{pkg['name']} [{','.join(target['kind'])}] {src.relative_to(ROOT).as_posix()}")
    if missing:
        print(f"missing {MARK}:")
        for m in missing:
            print(f"  - {m}")
        return 1
    print(f"forbid(unsafe_code) check passed ({count} targets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

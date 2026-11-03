"""제품 사본이 고정한 하네스 판과 같은지 검사 (PM 2026-11-03 하네스 한곳으로, 근거 하네스 docs/design.md › 제품과 나누는 법).

관문·규약·AI 스킬의 정본은 하네스(policy/gates.*, policy/conventions/, skills/)이고, 제품에는 워커가 읽는 자리에 사본을 둔다
(docs/policy/gates.*, docs/policy/conventions/, .claude/skills/). 사본만 고치면 검사와 규칙이 갈라지므로, 제품 harness.lock
판의 하네스와 한 글자라도 다르거나 한쪽에만 있는 파일을 알린다. 줄 끝(CRLF/LF)은 같게 본다.

--warn이면 `경고:`로 시작하는 줄만 내고 0으로 끝난다(처음에는 경고, 진행 중인 묶음이 들어온 뒤 실패로 올림).
아니면 `파일:1: 이유`를 한 줄씩 내고 1로 끝난다.

사용: python3 -X utf8 ci/check-harness-copies.py [--warn] [제품 루트] [하네스 루트]
하네스 루트가 없으면 MOOKKO_HARNESS_DIR(제품 scripts/harness.sh가 넘김), 그것도 없으면 이 파일의 하네스.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# (하네스 안 경로, 제품 안 경로, 맞추지 않는 하네스 쪽 파일). 폴더면 그 아래 파일 전부를 맞춘다.
# skills/README.md는 하네스 폴더 안내라 제품에 옮기지 않는다.
PAIRS = (
    ("policy/gates.md", "docs/policy/gates.md", ()),
    ("policy/gates.json", "docs/policy/gates.json", ()),
    ("policy/conventions", "docs/policy/conventions", ()),
    ("skills", ".claude/skills", ("README.md",)),
)


def files(base: Path) -> dict[str, Path]:
    if base.is_file():
        return {"": base}
    if not base.is_dir():
        return {}
    return {p.relative_to(base).as_posix(): p for p in sorted(base.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def same(a: Path, b: Path) -> bool:
    return a.read_bytes().replace(b"\r\n", b"\n") == b.read_bytes().replace(b"\r\n", b"\n")


def problems(product: Path, harness: Path) -> list[str]:
    found: list[str] = []
    for h_rel, p_rel, skip in PAIRS:
        h_files, p_files = files(harness / h_rel), files(product / p_rel)
        h_files = {k: v for k, v in h_files.items() if k not in skip}
        if not h_files:
            found.append(f"{p_rel}:1: 하네스에 정본 {h_rel}이 없습니다(harness.lock 판 확인)")
            continue
        for key in sorted(set(h_files) | set(p_files)):
            shown = f"{p_rel}/{key}" if key else p_rel
            h_name = f"{h_rel}/{key}" if key else h_rel
            if key not in p_files:
                found.append(f"{shown}:1: 제품 사본이 없습니다. 하네스 {h_name}을 그대로 옮기세요")
            elif key not in h_files:
                found.append(f"{shown}:1: 하네스 정본에 없는 파일입니다. 하네스 {h_name}에 넣고 harness.lock을 올리세요")
            elif not same(h_files[key], p_files[key]):
                found.append(f"{shown}:1: 고정 판의 하네스 {h_name}과 다릅니다. 하네스를 고치고 harness.lock을 올린 뒤 사본을 맞추세요")
    return found


def main(argv: list[str]) -> int:
    warn = "--warn" in argv
    args = [a for a in argv if a != "--warn"]
    product = Path(args[0]).resolve() if args else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    if len(args) > 1:
        harness = Path(args[1]).resolve()
    else:
        harness = Path(os.environ.get("MOOKKO_HARNESS_DIR") or Path(__file__).resolve().parents[1]).resolve()
    found = problems(product, harness)
    if found and not warn:
        for line in found:
            print(line)
        print(f"harness copy check failed ({len(found)} problems)")
        return 1
    for line in found:
        print(f"경고: {line}")
    print(f"harness copy check passed ({len(PAIRS)} pairs, {len(found)} warnings{', warn only' if warn else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

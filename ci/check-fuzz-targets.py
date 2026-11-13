"""fuzz 대상 목록과 코드 대조 (TEST-01, rust-qa 11-13 보통 2, 백로그 9o).

제품 fuzz/targets.json은 "하네스가 이 목록으로 대조한다"고 적혀 있었지만 그런 검사가 없었고, 목록 6개와 코드 4개가 달랐다.
이 검사는 fuzz/ 아래 세 곳을 맞춰 본다.
- targets.json의 대상마다 fuzz/fuzz_targets/<name>.rs가 있어야 한다. 없으면 경고(L4 전 필수, `--l4`면 실패).
- fuzz/fuzz_targets/*.rs는 모두 targets.json에 있어야 한다(목록 밖 대상은 실행 기록·관문 대조가 빠짐). 없으면 실패.
- 코드가 있는 대상마다 fuzz/Cargo.toml에 같은 이름의 [[bin]]이 path `fuzz_targets/<name>.rs`로 있어야 한다. 아니면 실패.
  [[bin]]이 가리키는 파일이 없거나 목록에 없는 [[bin]]도 실패.
- targets.json 칸: targets[] 마다 name·crate·entry·owner(빈 글 아님), name은 겹치지 않음. gate의 키는 targets에 있는 이름.
fuzz/가 없으면 검사할 것이 없어 통과한다. 빌드(cargo fuzz build)는 nightly·cargo-fuzz 설치 결정 뒤에 따로 넣는다.
실패는 `파일:줄: 이유`를 한 줄씩 내고 1, 경고는 `경고:`로 시작하는 줄.

사용: python3 -X utf8 ci/check-fuzz-targets.py [제품 루트] [--l4]
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    l4 = "--l4" in argv
    root = Path(args[0]).resolve() if args else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    fuzz = root / "fuzz"
    if not fuzz.is_dir():
        print("fuzz target check passed (fuzz/ 없음)")
        return 0
    problems: list[str] = []
    warnings: list[str] = []
    try:
        listed = json.loads((fuzz / "targets.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"fuzz/targets.json:1: 읽지 못했습니다: {error}")
        print("fuzz target check failed (1 problems)")
        return 1
    names: list[str] = []
    for item in listed.get("targets") or []:
        if not isinstance(item, dict):
            problems.append("fuzz/targets.json:1: targets 항목은 객체여야 합니다")
            continue
        missing = [k for k in ("name", "crate", "entry", "owner") if not (isinstance(item.get(k), str) and item[k].strip())]
        if missing:
            problems.append(f"fuzz/targets.json:1: 대상 {item.get('name')!r}에 {missing} 칸이 없습니다")
            continue
        if item["name"] in names:
            problems.append(f"fuzz/targets.json:1: 대상 이름 {item['name']}가 겹칩니다")
            continue
        names.append(item["name"])
    for key in (listed.get("gate") or {}):
        if key not in names:
            problems.append(f"fuzz/targets.json:1: gate의 {key}는 targets에 없는 대상입니다")
    code = {p.stem for p in (fuzz / "fuzz_targets").glob("*.rs")} if (fuzz / "fuzz_targets").is_dir() else set()
    try:
        manifest = tomllib.loads((fuzz / "Cargo.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        problems.append(f"fuzz/Cargo.toml:1: 읽지 못했습니다: {error}")
        manifest = {}
    bins = {b.get("name"): b.get("path") for b in manifest.get("bin") or [] if isinstance(b, dict)}
    for name in names:
        if name not in code:
            (problems if l4 else warnings).append(
                f"fuzz/targets.json:1: 대상 {name}의 코드 fuzz/fuzz_targets/{name}.rs가 없습니다(L4 전 필수, TEST-01)")
    for name in sorted(code - set(names)):
        problems.append(f"fuzz/fuzz_targets/{name}.rs:1: targets.json에 없는 대상입니다(실행 기록·관문 대조가 빠짐)")
    for name in sorted(code & set(names)):
        if bins.get(name) != f"fuzz_targets/{name}.rs":
            problems.append(f"fuzz/Cargo.toml:1: 대상 {name}의 [[bin]](path fuzz_targets/{name}.rs)이 없거나 경로가 다릅니다")
    for name, path in sorted(bins.items(), key=lambda kv: str(kv[0])):
        if name not in names:
            problems.append(f"fuzz/Cargo.toml:1: [[bin]] {name}는 targets.json에 없는 대상입니다")
        elif not path or not (fuzz / path).is_file():
            problems.append(f"fuzz/Cargo.toml:1: [[bin]] {name}의 path {path!r} 파일이 없습니다")
    for p in problems:
        print(p)
    for w in warnings:
        print(f"경고: {w}")
    if problems:
        print(f"fuzz target check failed ({len(problems)} problems)")
        return 1
    print(f"fuzz target check passed ({len(names)} targets, {len(code)} with code, {len(warnings)} warnings{', l4' if l4 else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

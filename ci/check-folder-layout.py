"""하네스 저장소 폴더 자리 검사 (PM 2026-11-03 "알맞은 폴더로 다 정리", 근거 하네스 docs/design.md › 폴더).

하네스 최상위에는 정한 폴더·파일만 두고, 폴더마다 README.md(여기 두는 것 / 두지 않는 것)를 둔다. 폴더별로 둘 수 있는 파일
종류를 정해, 검사 스크립트가 규칙 폴더에 들어가거나 설정이 코드 폴더에 흩어지는 것을 막는다. 실행 데이터(data/)·빌드
산출물(target/)·git은 보지 않는다.

--warn이면 `경고:`로 시작하는 줄만 내고 0으로 끝난다(처음에는 경고). 아니면 `파일:1: 이유`를 한 줄씩 내고 1로 끝난다.

사용: python3 -X utf8 ci/check-folder-layout.py [--warn] [하네스 루트]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_FILES = {"README.md", "Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "rustfmt.toml", "clippy.toml", "deny.toml",
              ".gitignore", ".gitattributes", ".complete"}
SKIP = {".git", "data", "target", "__pycache__", ".claude"}
# 최상위 폴더 → 둘 수 있는 확장자(None이면 아무것이나). README.md는 어디나 됨.
FOLDERS: dict[str, set[str] | None] = {
    "docs": {".md", ".json", ".py", ".txt"},  # reference/ 아래 옛 판 기록·도구 포함
    "policy": {".md", ".json"},
    "rules": {".md"},
    "skills": {".md"},
    "ci": None,  # 검사 표본(fixtures/)이 여러 종류를 흉내 냄
    "dev": {".sh", ".py"},
    "config": {".json"},
    "apps": None,
    "crates": None,
}


def problems(root: Path) -> list[str]:
    found: list[str] = []
    for entry in sorted(root.iterdir()):
        if entry.name in SKIP:
            continue
        if entry.is_file():
            if entry.name not in ROOT_FILES:
                found.append(f"{entry.name}:1: 최상위에 둘 파일이 아닙니다(정한 폴더로 옮기세요: docs/design.md › 폴더)")
            continue
        if entry.name not in FOLDERS:
            found.append(f"{entry.name}/:1: 정하지 않은 최상위 폴더입니다(docs/design.md › 폴더에 먼저 적으세요)")
            continue
        if not (entry / "README.md").is_file():
            found.append(f"{entry.name}/README.md:1: 폴더 안내가 없습니다(여기 두는 것 / 두지 않는 것)")
        allowed = FOLDERS[entry.name]
        if allowed is None:
            continue
        for path in sorted(entry.rglob("*")):
            if not path.is_file() or SKIP.intersection(path.relative_to(root).parts) or path.name == "README.md":
                continue
            if path.suffix not in allowed:
                rel = path.relative_to(root).as_posix()
                found.append(f"{rel}:1: {entry.name}/에는 {', '.join(sorted(allowed))} 파일만 둡니다")
    return found


def main(argv: list[str]) -> int:
    warn = "--warn" in argv
    args = [a for a in argv if a != "--warn"]
    root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[1]
    found = problems(root)
    if found and not warn:
        for line in found:
            print(line)
        print(f"folder layout check failed ({len(found)} problems)")
        return 1
    for line in found:
        print(f"경고: {line}")
    print(f"folder layout check passed ({len(FOLDERS)} folders, {len(found)} warnings{', warn only' if warn else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

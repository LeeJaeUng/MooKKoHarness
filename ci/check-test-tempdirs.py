"""시험 임시 폴더 검사 (tools.md T-SH-3, CLAUDE.md › WSL 시험 임시 폴더 예외 2026-11-02).

Linux에는 휴지통이 없어서, 시험이 같은 실행에서 직접 만든 `$TMPDIR/mookko-test/...` 아래 폴더만 바로 지울 수 있고
실패한 시험의 폴더는 원인 확인용으로 남겨야 한다. 시험 코드가 그 밖의 경로를 만들거나 지우지 못하게 잡는다.
- Rust(crates/·acceptance/): `temp_dir()` 바로 뒤 첫 `.join(...)`은 `"mookko-test"`여야 한다.
- Rust(crates/·acceptance/): `remove_dir_all`을 부르는 `impl Drop`은 `std::thread::panicking()`일 때 지우지 않아야 한다
  (그 블록 안에 `std::thread::panicking()`이 있어야 함).
- Bash(scripts/·crates/의 *.sh): `rm -r`의 대상은 `"$변수"` 하나여야 하고, 그 변수를 따라가면 값에 `mookko-test`가 있어야 한다.
- 실패하면 `파일:줄: 이유`를 한 줄씩 내고 1로 끝난다.

사용: python3 -X utf8 ci/check-test-tempdirs.py [저장소 루트]  (루트를 주면 표본 폴더를 검사할 수 있음)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist"}

TEMP_DIR = re.compile(r"temp_dir\(\)")
FIRST_JOIN = re.compile(r'\s*\.join\(\s*"mookko-test"\s*\)')
IMPL_DROP = re.compile(r"\bimpl\b[^{;]*\bDrop\s+for\b[^{]*\{")
RM_RECURSIVE = re.compile(r"(?:^|[;&|\s])rm\s+(-[a-zA-Z]*[rR][a-zA-Z]*)(?:\s+--)?\s+(.+?)\s*(?:$|[;&|#])")
RM_TARGET = re.compile(r'^"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?"$')
ASSIGN = re.compile(r"^\s*(?:local\s+|export\s+|readonly\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
VAR_REF = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)")


def files(root: Path, base: Path, suffix: str):
    if not base.exists():
        return
    for path in sorted(base.rglob(f"*{suffix}")):
        rel = path.relative_to(root)
        if path.is_file() and not any(p in SKIP_DIRS for p in rel.parts):
            yield path, rel


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def block_end(text: str, open_brace: int) -> int:
    depth = 0
    for i in range(open_brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def check_rust(rel: Path, text: str, problems: list[str]) -> None:
    for m in TEMP_DIR.finditer(text):
        if not FIRST_JOIN.match(text, m.end()):
            problems.append(f"{rel.as_posix()}:{line_of(text, m.start())}: temp_dir() 바로 뒤에 .join(\"mookko-test\")가 와야 합니다")
    for m in IMPL_DROP.finditer(text):
        body = text[m.end() - 1 : block_end(text, m.end() - 1) + 1]
        if "remove_dir_all" in body and "std::thread::panicking()" not in body:
            problems.append(
                f"{rel.as_posix()}:{line_of(text, m.start())}: 폴더를 지우는 Drop은 std::thread::panicking()이면 지우지 않고 남겨야 합니다"
            )


def mentions_test_root(var: str, assigns: dict[str, list[str]], seen: set[str]) -> bool:
    if var in seen:
        return False
    seen.add(var)
    values = assigns.get(var, [])
    if not values:
        return False
    for value in values:
        if "mookko-test" in value:
            continue
        refs = [r for r in VAR_REF.findall(value) if r in assigns]
        if not any(mentions_test_root(r, assigns, seen) for r in refs):
            return False
    return True


def check_shell(rel: Path, text: str, problems: list[str]) -> None:
    lines = text.splitlines()
    assigns: dict[str, list[str]] = {}
    for line in lines:
        a = ASSIGN.match(line)
        if a:
            assigns.setdefault(a.group(1), []).append(a.group(2))
    for no, line in enumerate(lines, 1):
        if line.lstrip().startswith("#"):
            continue
        for m in RM_RECURSIVE.finditer(line):
            target = RM_TARGET.match(m.group(2).strip())
            where = f"{rel.as_posix()}:{no}"
            if not target:
                problems.append(f"{where}: rm -r 대상은 \"$변수\" 하나여야 합니다: {m.group(2).strip()}")
            elif not mentions_test_root(target.group(1), assigns, set()):
                problems.append(f"{where}: rm -r 대상 ${target.group(1)}이 $TMPDIR/mookko-test/ 아래 경로로 정해지지 않았습니다")


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    problems: list[str] = []
    scanned = 0
    for base in (root / "crates", root / "acceptance"):  # 인수 시험 실행기도 봄(RustDev 11-03)
        for path, rel in files(root, base, ".rs"):
            scanned += 1
            check_rust(rel, path.read_text(encoding="utf-8"), problems)
    for base in (root / "scripts", root / "crates", root / "acceptance"):
        for path, rel in files(root, base, ".sh"):
            scanned += 1
            check_shell(rel, path.read_text(encoding="utf-8"), problems)
    for p in problems:
        print(p)
    if problems:
        print(f"test temp folder check failed ({len(problems)} problems)")
        return 1
    print(f"test temp folder check passed ({scanned} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""proto 호환 대조 — buf 도입 전 대안(rust-qa 11-14 DEP-2, 백로그 9z; 규약 policy/conventions/proto.md P-COMPAT-1).

제품 proto/ 아래 .proto를 기준 판(MOOKKO_REGISTER_BASE, 기본 foundation/engine)의 같은 파일과 견준다. 두 판이 함께 도는 gRPC 배포에서
옛 판이 새 판의 메시지를 잘못 읽는 변경을 찾는다.
- 메시지 필드: 같은 번호의 이름·형·꼴(repeated/optional/map)이 바뀜, 지운 필드의 번호와 이름이 둘 다 `reserved`가 아님.
- 열거형 값: 같은 번호의 이름이 바뀜, 지운 값의 번호가 `reserved`가 아님.
- 지움: 메시지·열거형·.proto 파일·서비스 RPC를 지움(깨지는 변경은 새 `v2` 패키지로, P-COMPAT-2), RPC의 요청·응답 형이 바뀜.
- 늘리기(새 필드·값·메시지·RPC)는 통과.
완전한 proto 파서가 아니라 정해진 모양을 읽는다(주석을 떼고 message·enum·service 블록과 필드 줄). buf breaking이 들어오면 그것으로 바꾼다.
처음에는 경고만(`경고:` 줄, 종료 0). `--l4`(출시 관문, ci/check-l4.sh)에서는 실패(`proto/…:1: 이유`, 종료 1).
검사 폴더가 git 최상위가 아니면(표본) 건너뛰고, 기준 판을 못 읽으면 MOOKKO_REQUIRE_GIT_HISTORY=1에서 실패.

사용: python3 -X utf8 ci/check-proto-compat.py [제품 루트] [--l4]
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

FIELD = re.compile(r"^(?:(repeated|optional)\s+)?(map\s*<[^>]+>|[\w.]+)\s+(\w+)\s*=\s*(\d+)\s*(?:\[.*\])?\s*;$", re.S)
ENUM_VALUE = re.compile(r"^(\w+)\s*=\s*(-?\d+)\s*(?:\[.*\])?\s*;$", re.S)
RPC = re.compile(r"^rpc\s+(\w+)\s*\(\s*(stream\s+)?([\w.]+)\s*\)\s*returns\s*\(\s*(stream\s+)?([\w.]+)\s*\)", re.S)


@dataclass
class Block:
    kind: str  # message | enum | service
    fields: dict[int, tuple[str, str, str]] = field(default_factory=dict)  # 번호 → (이름, 형, 꼴)
    values: dict[int, str] = field(default_factory=dict)  # 열거형 번호 → 이름
    rpcs: dict[str, tuple[str, str]] = field(default_factory=dict)  # RPC 이름 → (요청, 응답) 형(stream 표시 포함)
    reserved_numbers: set[int] = field(default_factory=set)
    reserved_names: set[str] = field(default_factory=set)


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def parse_reserved(stmt: str, block: Block) -> None:
    body = stmt[len("reserved"):].strip().rstrip(";")
    for part in body.split(","):
        part = part.strip()
        if part.startswith(("\"", "'")):
            block.reserved_names.add(part.strip("\"'"))
            continue
        m = re.fullmatch(r"(\d+)\s+to\s+(\d+|max)", part)
        if m:
            end = int(m.group(2)) if m.group(2) != "max" else int(m.group(1)) + 10_000
            block.reserved_numbers.update(range(int(m.group(1)), end + 1))
        elif part.isdigit():
            block.reserved_numbers.add(int(part))


def parse(text: str) -> dict[str, Block]:
    """{전체 이름(message·enum은 바깥 이름을 점으로 이음, service는 'service:이름'): Block}."""
    text = strip_comments(text)
    blocks: dict[str, Block] = {}
    stack: list[tuple[str, Block | None]] = []  # (이름, 블록 — oneof·option 블록은 None이고 바깥 메시지에 필드를 넣음)
    i = 0
    buf = ""
    square = 0  # [ ] 안(필드 옵션)은 { } ; 를 글자로
    literal = 0  # `option … = {` 꼴 값의 { } 깊이(글자로 모음)
    while i < len(text):
        ch = text[i]
        if square or literal:
            buf += ch
            if square:
                square += {"[": 1, "]": -1}.get(ch, 0)
            elif ch == "{":
                literal += 1
            elif ch == "}":
                literal -= 1
            i += 1
            continue
        if ch == "[":
            square = 1
            buf += ch
            i += 1
            continue
        if ch == "{" and re.search(r"=\s*$", buf):
            literal = 1  # option (x) = { … } 값
            buf += ch
            i += 1
            continue
        if ch == "{":
            head = buf.strip()
            buf = ""
            m = re.match(r"^(message|enum|service|oneof)\s+(\w+)$", head)
            if m and m.group(1) in ("message", "enum"):
                outer = ".".join(n for n, b in stack if b is not None and b.kind in ("message", "enum"))
                name = f"{outer}.{m.group(2)}" if outer else m.group(2)
                block = Block(m.group(1))
                blocks[name] = block
                stack.append((m.group(2), block))
            elif m and m.group(1) == "service":
                block = Block("service")
                blocks[f"service:{m.group(2)}"] = block
                stack.append((m.group(2), block))
            else:
                stack.append(("", None))  # oneof·option·rpc 본문 등
        elif ch == "}":
            buf = ""
            if stack:
                stack.pop()
        elif ch == ";":
            stmt = " ".join((buf + ";").split())
            buf = ""
            owner = next((b for _, b in reversed(stack) if b is not None), None)
            if owner is None:
                pass
            elif stmt.startswith("reserved "):
                parse_reserved(stmt, owner)
            elif owner.kind == "message":
                f = FIELD.match(stmt)
                if f and not stmt.startswith(("option ", "extensions ")):
                    owner.fields[int(f.group(4))] = (f.group(3), " ".join(f.group(2).split()), f.group(1) or "")
            elif owner.kind == "enum":
                v = ENUM_VALUE.match(stmt)
                if v and not stmt.startswith("option "):
                    owner.values[int(v.group(2))] = v.group(1)
            elif owner.kind == "service":
                r = RPC.match(stmt)
                if r:
                    owner.rpcs[r.group(1)] = (f"{r.group(2) or ''}{r.group(3)}", f"{r.group(4) or ''}{r.group(5)}")
        else:
            buf += ch
            # rpc X (...) returns (...) { option ...; } 꼴: 여는 괄호 앞에서 rpc 문장을 끊음
            if ch == ")" and re.match(r"^\s*rpc\s", buf) and re.search(r"returns\s*\([^)]*\)\s*$", buf):
                stmt = " ".join(buf.split())
                owner = next((b for _, b in reversed(stack) if b is not None), None)
                r = RPC.match(stmt)
                if owner is not None and owner.kind == "service" and r:
                    owner.rpcs[r.group(1)] = (f"{r.group(2) or ''}{r.group(3)}", f"{r.group(4) or ''}{r.group(5)}")
                buf = ""
        i += 1
    return blocks


def compare(rel: str, old: dict[str, Block], new: dict[str, Block]) -> list[str]:
    problems: list[str] = []
    for name, ob in sorted(old.items()):
        nb = new.get(name)
        what = "서비스" if ob.kind == "service" else ("메시지" if ob.kind == "message" else "열거형")
        if nb is None:
            problems.append(f"{rel}:1: {what} {name.removeprefix('service:')}를 지웠습니다(깨지는 변경은 새 v2 패키지로, P-COMPAT-2)")
            continue
        if ob.kind == "message":
            for num, (fname, ftype, label) in sorted(ob.fields.items()):
                now = nb.fields.get(num)
                if now is None:
                    if num not in nb.reserved_numbers or fname not in nb.reserved_names:
                        problems.append(f"{rel}:1: {name}.{fname}(={num})을 지웠는데 번호와 이름이 reserved가 아닙니다(P-COMPAT-1)")
                elif now != (fname, ftype, label):
                    problems.append(f"{rel}:1: {name} 필드 번호 {num}이 {label} {ftype} {fname} → {now[2]} {now[1]} {now[0]}로 바뀌었습니다(P-COMPAT-1)")
        elif ob.kind == "enum":
            for num, vname in sorted(ob.values.items()):
                now = nb.values.get(num)
                if now is None and num not in nb.reserved_numbers:
                    problems.append(f"{rel}:1: {name} 값 {vname}(={num})을 지웠는데 번호가 reserved가 아닙니다(P-COMPAT-1)")
                elif now is not None and now != vname:
                    problems.append(f"{rel}:1: {name} 값 번호 {num}의 이름이 {vname} → {now}로 바뀌었습니다(P-COMPAT-1)")
        else:
            for rpc, sig in sorted(ob.rpcs.items()):
                now = nb.rpcs.get(rpc)
                if now is None:
                    problems.append(f"{rel}:1: {name.removeprefix('service:')}.{rpc} RPC를 지웠습니다(P-COMPAT-2)")
                elif now != sig:
                    problems.append(f"{rel}:1: {name.removeprefix('service:')}.{rpc}의 요청·응답 형이 {sig} → {now}로 바뀌었습니다(P-COMPAT-1)")
    return problems


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    l4 = "--l4" in argv
    root = Path(args[0]).resolve() if args else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    required = os.environ.get("MOOKKO_REQUIRE_GIT_HISTORY") == "1"
    top = git(root, "rev-parse", "--show-toplevel")
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root:
        print("proto compat check passed (git 밖 — 견줄 기준 판 없음)")
        return 0
    base = os.environ.get("MOOKKO_REGISTER_BASE") or "foundation/engine"
    listed = git(root, "ls-tree", "-r", "--name-only", base, "--", "proto")
    if listed.returncode != 0:
        line = f"proto/:1: 기준 판 {base}의 proto 목록을 읽지 못했습니다: {listed.stderr.strip()[:200]}"
        if required:
            print(line)
            print("proto compat check failed (1 problems)")
            return 1
        print(f"경고: {line}")
        print("proto compat check passed (기준 판 비교 건너뜀)")
        return 0
    problems: list[str] = []
    old_files = [p for p in listed.stdout.split() if p.endswith(".proto")]
    for rel in old_files:
        shown = git(root, "show", f"{base}:{rel}")
        path = root / rel
        if not path.exists():
            problems.append(f"{rel}:1: proto 파일을 지웠습니다(깨지는 변경은 새 v2 패키지로, P-COMPAT-2)")
            continue
        problems += compare(rel, parse(shown.stdout), parse(path.read_text(encoding="utf-8")))
    for p in problems:
        print(p if l4 else f"경고: {p}")
    if problems and l4:
        print(f"proto compat check failed ({len(problems)} problems, L4)")
        return 1
    mode = "L4" if l4 else "warn only"
    print(f"proto compat check passed ({len(old_files)} files against {base}, {len(problems)} findings, {mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

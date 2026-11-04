"""보안 설계 검토 기록 검사 (하네스 policy/conventions/security.md SC-REV-1·3, 보안 담당 요청 2026-11-04 QA N5).

설계서의 `security:reviewed` 줄은 안내이고, 출시 관문(L4)의 근거는 제품 docs/policy/security-reviews.json(보안 담당만 고침)이다.
- 등록부가 없으면 실패(SC-REG-1과 같음). 항목마다 path·section·sha256·verdict(reviewed|changes)·date·reviewer·reviewedAt·what
- 항목의 절(머리줄 글이 section인 머리줄부터, 같은 단계 이하의 다음 머리줄 앞까지, 줄 끝 공백을 지우고 절 끝 빈 줄은 빼고 `\\n`으로 이은 UTF-8)의
  sha256을 다시 계산해 다르면 "만료"(보안 담당이 다시 봄). 파일이나 절이 없어도 만료
- 저장소 안 .md에 `security:reviewed` 줄이 있는데 그 줄이 든 절(가장 가까운 위 머리줄)의 reviewed 기록이 없으면 "기록 없음"
- 만료·기록 없음은 경고이고, `--l4`(또는 MOOKKO_L4=1, 출시 관문)에서는 실패. 칸·모양이 틀린 항목은 늘 실패
- path는 저장소 안 상대 경로만(절대 경로·`..` 금지)
- 기준 판(MOOKKO_REGISTER_BASE, 기본 foundation/engine)과 대조(mookko-rust-qa 11-04): 기준 판의 (path, section) 항목이 사라지거나,
  sha256이 바뀌었는데 reviewedAt(검토한 커밋)이 그대로면(다시 보지 않고 해시만 고침) 실패, date를 되돌리면 실패(같은 날 다시 보는 것은 됨).
  검사 폴더가 git 최상위가 아니면(표본) 대조하지 않고, git·기준 판을 읽지 못하면 MOOKKO_REQUIRE_GIT_HISTORY=1일 때 실패
`경고:`로 시작하는 줄은 경고, `파일:줄: 이유`는 실패.

사용: python3 -X utf8 ci/check-security-reviews.py [--l4] [저장소 루트]
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REL = "docs/policy/security-reviews.json"
FIELDS = ("path", "section", "sha256", "verdict", "date", "reviewer", "reviewedAt", "what")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist"}
MARK = "security:reviewed"


def headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(줄 번호 0부터, 단계, 머리줄 글). 코드 울타리(```) 안은 뺀다."""
    out: list[tuple[int, int, str]] = []
    fenced = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        m = None if fenced else HEADING.match(line)
        if m:
            out.append((i, len(m.group(1)), m.group(2)))
    return out


def section_text(lines: list[str], title: str) -> str | None:
    marks = headings(lines)
    for n, (i, level, text) in enumerate(marks):
        if text == title:
            end = next((j for j, lv, _ in marks[n + 1:] if lv <= level), len(lines))
            body = [line.rstrip() for line in lines[i:end]]
            while body and not body[-1]:
                body.pop()  # 절 끝의 빈 줄은 뺌(보안 담당 계산과 같음)
            return "\n".join(body)
    return None


def section_of(lines: list[str], line_no: int) -> str | None:
    """line_no(0부터)가 든 절의 머리줄 글(가장 가까운 위 머리줄)."""
    marks = [text for i, _, text in headings(lines) if i <= line_no]
    return marks[-1] if marks else None


NOT_TOP = "검사 폴더가 git 최상위가 아님(표본)"


def git(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")
    return result.stdout if result.returncode == 0 else None


def compare_base(root: Path, reviews: list) -> list[str]:
    """기준 판 기록과 대조: 사라짐·다시 보지 않은 해시 바꾸기·날짜 되돌리기."""
    top = git(root, "rev-parse", "--show-toplevel")
    required = os.environ.get("MOOKKO_REQUIRE_GIT_HISTORY") == "1"
    if top is None or Path(top.strip()).resolve() != root:
        if top is None and required:
            return [f"{REL}:1: 기준 판과 대조하지 못했습니다(git을 읽지 못함)"]
        if top is not None:
            return []  # 표본
        print("기준 판 대조 건너뜀(통과 아님): git을 읽지 못함")
        return []
    ref = os.environ.get("MOOKKO_REGISTER_BASE") or "foundation/engine"
    if git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is None:
        return [f"{REL}:1: 기준 판 {ref}를 읽지 못했습니다"] if required else []
    text = git(root, "show", f"{ref}:{REL}")
    if text is None:
        return []
    try:
        old = json.loads(text).get("reviews") or []
    except (ValueError, AttributeError):
        return [f"{REL}:1: 기준 판 {ref}의 검토 기록 JSON이 깨져 있습니다"]
    now = {(r.get("path"), r.get("section")): r for r in reviews if isinstance(r, dict)}
    out = []
    for prev in old:
        if not isinstance(prev, dict):
            continue
        key = (prev.get("path"), prev.get("section"))
        cur = now.get(key)
        name = f"{key[0]} › {key[1]}"
        if cur is None:
            out.append(f"{REL}:1: {name}: 기준 판에 있던 검토 기록이 사라졌습니다(지우지 않고 verdict·날짜로 고침)")
            continue
        if str(cur.get("date", "")) < str(prev.get("date", "")):
            out.append(f"{REL}:1: {name}: date를 기준 판 {prev.get('date')}보다 앞으로 되돌렸습니다")
        if cur.get("sha256") != prev.get("sha256") and cur.get("reviewedAt") == prev.get("reviewedAt"):
            out.append(f"{REL}:1: {name}: sha256이 바뀌었는데 reviewedAt이 그대로입니다(다시 볼 때는 검토한 새 커밋을 적음, 해시만 고치지 않음)")
    return out


def main(argv: list[str]) -> int:
    l4 = "--l4" in argv or os.environ.get("MOOKKO_L4") == "1"
    args = [a for a in argv if not a.startswith("--")]
    root = Path(args[0]).resolve() if args else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    path = root / REL
    if not path.exists():
        print(f"{REL}:1: 보안 검토 기록이 없습니다(늘 있어야 함, SC-REG-1·SC-REV-3)")
        print("security review check failed (1 problems)")
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"{REL}:1: JSON을 읽지 못했습니다: {e}")
        print("security review check failed (1 problems)")
        return 1
    problems: list[str] = []
    soft: list[str] = []
    reviewed: set[tuple[str, str]] = set()
    reviews = data.get("reviews") if isinstance(data, dict) else None
    if not isinstance(reviews, list):
        problems.append(f"{REL}:1: `reviews` 목록이 없습니다")
        reviews = []
    for i, item in enumerate(reviews):
        if not (isinstance(item, dict) and all(item.get(k) for k in FIELDS)):
            problems.append(f"{REL}:1: reviews[{i}]에 {'·'.join(FIELDS)}가 있어야 합니다")
            continue
        name = f"{item['path']} › {item['section']}"
        if Path(item["path"]).is_absolute() or ".." in Path(item["path"]).parts:
            problems.append(f"{REL}:1: {name}: path는 저장소 안 상대 경로여야 합니다")
            continue
        if item["verdict"] not in ("reviewed", "changes") or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            problems.append(f"{REL}:1: {name}: verdict는 reviewed|changes, sha256은 소문자 64자")
            continue
        try:
            datetime.date.fromisoformat(item["date"])
        except ValueError:
            problems.append(f"{REL}:1: {name}: date가 YYYY-MM-DD가 아닙니다")
        doc = root / item["path"]
        text = section_text(doc.read_text(encoding="utf-8").splitlines(), item["section"]) if doc.is_file() else None
        if text is None:
            soft.append(f"{REL}:1: {name}: 그 파일·절이 없습니다(검토 만료, 보안 담당이 다시 봄)")
            continue
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != item["sha256"]:
            soft.append(f"{REL}:1: {name}: 절 내용이 검토 뒤 바뀌었습니다(sha256 다름, 검토 만료 — 보안 담당이 다시 봄)")
            continue
        if item["verdict"] == "reviewed":
            reviewed.add((item["path"], item["section"]))
    problems += compare_base(root, reviews)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for filename in sorted(filenames):
            if not filename.endswith(".md"):
                continue
            file = Path(dirpath) / filename
            rel = file.relative_to(root).as_posix()
            lines = file.read_text(encoding="utf-8").splitlines()
            for n, line in enumerate(lines):
                if MARK in line and not line.lstrip().startswith(("|", "-   ", ">")) and "`security:reviewed" not in line:
                    title = section_of(lines, n)
                    if title is not None and (rel, title) not in reviewed:
                        soft.append(f"{rel}:{n + 1}: `{MARK}` 줄이 있지만 {REL}에 이 절({title})의 유효한 reviewed 기록이 없습니다")
    for line in problems:
        print(line)
    for line in soft:
        print(line if l4 else f"경고: {line}")
    failed = problems + (soft if l4 else [])
    mode = "L4" if l4 else "warn only"
    if failed:
        print(f"security review check failed ({len(failed)} problems, {mode})")
        return 1
    print(f"security review check passed ({len(reviews)} reviews, {len(soft)} warnings, {mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

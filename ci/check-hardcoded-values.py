"""박아 넣은 숫자·기계 전용 경로 검사 (PM 사용자 대행 2026-11-03, 사용자 "지금 코드를 훝고있는데 하드코딩으로 경로같은거
들어간거 뭐야", "숫자도 다 하드코딩으로 쳐넣어났네"; 근거 docs/policy/conventions/rust.md R-CFG-1·tools.md).

규칙
- DUR: Rust 시험 밖 코드의 `Duration::from_*(숫자)`. 운영에서 바꿀 값은 JSON 설정으로, 안전 상한은 이름 붙은 상수로.
- NUM: Rust 시험 밖 코드에서 `const`·`static` 정의 밖에 쓴 세 자리 이상 숫자(100 이상, 비교식 안 숫자 포함). 문자열·주석·
  속성(#[…]) 안은 보지 않는다.
- INC: `include_str!`·`include_bytes!`가 자기 crate 폴더 밖 파일을 읽음(엔진이 서비스 파일을 읽는 층 위반 등).
- PATH: 저장소 안 *.json·*.sh·*.py·*.toml·*.ps1·*.y(a)ml에 든 기계 전용 절대 경로(드라이브 문자 `X:/`·`X:\\`, `/mnt/<드라이브>/`,
  `/home/<사용자>/`, `/Users/<사용자>/`). 경로는 저장소 기준 상대 경로로, 기계마다 다른 값은 data/·환경 변수로.
시험 밖 코드: crates/·acceptance/ 아래 src/의 *.rs에서 crate 바로 아래 tests·benches·examples 폴더, `#[cfg(test)]` 항목,
적합성 시험 키트 crate(이름 끝 -conformance)를 뺀 것. const·static 정의 안은 이름 붙은 값이라 보지 않는다.

지금 있는 것은 docs/policy/hardcoded-values.json의 baseline(파일마다 규칙별 개수, 기한 expires)에 적어 두고 하나씩 옮긴다.
- enforce false(처음, PM 지시): 기준을 넘는 파일과 전체 개수를 `경고:`로 내고 0으로 끝난다.
- enforce true: 기준보다 많아진 파일은 그 파일의 해당 줄을 모두 `파일:줄: 이유`로 내고 실패. 기준보다 줄었으면 기준을 낮추라고
  실패(되돌아 늘지 않게). 기한이 지났는데 기준이 남아 있으면 실패.
`--list`는 걸린 줄을 모두 낸다(담당별 정리용). `--write-baseline`은 지금 개수로 baseline을 다시 쓴다(통합 담당만).

사용: python3 -X utf8 scripts/ci/check-hardcoded-values.py [저장소 루트] [--list] [--write-baseline]
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist", "fixtures"}
CRATE_SIDE_DIRS = {"tests", "benches", "examples"}
PATH_SUFFIXES = {".json", ".sh", ".py", ".toml", ".ps1", ".yml", ".yaml"}

DUR = re.compile(r"\bDuration::from_(?:secs|millis|micros|nanos|mins|hours|secs_f32|secs_f64)\(\s*[0-9]")
NUMBER = re.compile(r"(?<![\w.])(?:0x[0-9a-fA-F_]+|[0-9][0-9_]*(?:\.[0-9_]+)?)(?:[iuf](?:8|16|32|64|128|size))?(?![\w.])")
INCLUDE = re.compile(r"\binclude_(?:str|bytes)!\(\s*\"([^\"]+)\"")
MACHINE_PATH = re.compile(
    r"(?<![\w$])[A-Za-z]:[\\/]+[\w .-]+[\\/]"  # C:/Project/… · C:\Users\…
    r"|/mnt/[a-z]/"
    r"|/home/[a-z_][\w-]*/"
    r"|/Users/[\w.-]+/"
)
RULE_TEXT = {
    "DUR": "Duration에 숫자를 바로 넣었습니다. 운영에서 바꿀 값은 JSON 설정으로, 안전 상한은 이름 붙은 상수로 옮기세요",
    "NUM": "세 자리 이상 숫자를 const 밖에 바로 썼습니다. 설정이나 단위·근거를 적은 이름 붙은 상수로 옮기세요",
    "INC": "자기 crate 밖 파일을 include합니다. 시험 fixture는 crate 안에 두세요(층 위반)",
    "PATH": "기계 전용 절대 경로입니다. 저장소 기준 상대 경로로 바꾸고, 기계마다 다른 값은 data/·환경 변수로 빼세요",
}


def mask(text: str) -> str:
    """문자열·바이트 문자열·raw 문자열·문자 리터럴·주석의 내용을 공백으로 바꾼다(줄바꿈은 남김, 여러 줄 문자열도)."""
    out: list[str] = []
    i, n = 0, len(text)
    depth = 0  # 블록 주석 깊이

    def blank(s: str) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in s)

    while i < n:
        c = text[i]
        if depth:
            if text.startswith("*/", i):
                depth -= 1
                out.append("  ")
                i += 2
            elif text.startswith("/*", i):
                depth += 1
                out.append("  ")
                i += 2
            else:
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
            continue
        if text.startswith("/*", i):
            depth = 1
            out.append("  ")
            i += 2
            continue
        raw = re.match(r'b?r(#*)"', text[i:]) if c in "br" and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")) else None
        if raw:
            close = '"' + raw.group(1)
            j = text.find(close, i + raw.end())
            j = n if j == -1 else j + len(close)
            out.append(blank(text[i:j]))
            i = j
            continue
        if c == '"' or (c == "b" and text.startswith('b"', i) and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_"))):
            j = i + (2 if c == "b" else 1)
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            j = min(n, j + 1)
            out.append(blank(text[i:j]))
            i = j
            continue
        if c == "'":
            m = re.match(r"'(?:\\.[^']*|[^'\\\n])'", text[i:])
            if m:  # 문자 리터럴(생명 주기 'a는 닫는 따옴표가 없어 남김)
                out.append(" " * m.end())
                i += m.end()
                continue
        out.append(c)
        i += 1
    return "".join(out)


def code_lines(text: str):
    """`#[cfg(test)]` 항목을 뺀 (줄 번호, 원래 줄, 문자열·주석을 지운 줄)."""
    lines = text.splitlines()
    masked = mask(text).splitlines()
    i = 0
    while i < len(masked):
        if masked[i].lstrip().startswith("#[cfg(test)]"):
            depth, opened = 0, False
            j = i + 1 if masked[i].strip() == "#[cfg(test)]" else i
            while j < len(masked):
                s = masked[j]
                depth += s.count("{") - s.count("}")
                opened = opened or "{" in s
                if (opened and depth <= 0) or (not opened and s.rstrip().endswith(";")):
                    break
                j += 1
            i = j + 1
            continue
        yield i + 1, lines[i] if i < len(lines) else "", masked[i]
        i += 1


def in_src(rel: Path) -> bool:
    parts = rel.parts
    return "src" in parts and not any(p in CRATE_SIDE_DIRS for p in parts[: parts.index("src")])


def crate_dir(path: Path) -> Path:
    for parent in path.parents:
        if (parent / "Cargo.toml").exists():
            return parent
    return path.parent


def scan_include(root: Path, path: Path, hits: list[tuple[str, str, int, str]]) -> None:
    """시험 코드까지 모두 본다(시험이어도 다른 crate·서비스 파일을 읽으면 층 위반). 걸리는 것: 다른 crate 폴더의 파일,
    또는 엔진·어댑터 crate가 자기 폴더 밖(proto/ 제외)을 읽는 것. 서비스·앱 시험이 저장소 config/·proto/·docs/의 예시를
    읽는 것은 됨."""
    rel = path.relative_to(root).as_posix()
    home = crate_dir(path).resolve()
    crates_dir = (root / "crates").resolve()
    low_layer = rel.startswith(("crates/engine/", "crates/adapters/"))
    for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for m in INCLUDE.finditer(raw):
            target = (path.parent / m.group(1)).resolve()
            if home in target.parents:
                continue
            other_crate = crates_dir in target.parents
            outside_low = low_layer and (root / "proto").resolve() not in target.parents
            if other_crate or outside_low:
                hits.append((rel, "INC", no, raw.strip()))


def scan_rust(root: Path, path: Path, hits: list[tuple[str, str, int, str]]) -> None:
    rel = path.relative_to(root).as_posix()
    in_const = False
    for no, raw, code in code_lines(path.read_text(encoding="utf-8")):
        stripped = code.strip()
        if re.match(r"^(pub(\([\w:]+\))?\s+)?(const(?!\s+(unsafe\s+)?fn\b)|static)\s", stripped):
            in_const = True
        if not stripped.startswith("#[") and not stripped.startswith("#!["):
            if in_const:
                pass  # const·static 정의는 이름 붙은 값이라 됨
            elif DUR.search(code):
                hits.append((rel, "DUR", no, raw.strip()))
            else:
                for m in NUMBER.finditer(code):
                    digits = m.group(0).lower().replace("_", "")
                    digits = re.sub(r"[iuf](8|16|32|64|128|size)$", "", digits)
                    value = int(digits, 16) if digits.startswith("0x") else float(digits)
                    if value >= 100:
                        hits.append((rel, "NUM", no, raw.strip()))
                        break
        if in_const and stripped.endswith(";"):
            in_const = False


def scan(root: Path) -> list[tuple[str, str, int, str]]:
    hits: list[tuple[str, str, int, str]] = []
    for base in ("crates", "acceptance"):
        for path in sorted((root / base).rglob("*.rs")) if (root / base).exists() else []:
            rel = path.relative_to(root)
            if any(p in SKIP_DIRS for p in rel.parts):
                continue
            scan_include(root, path, hits)
            if in_src(rel) and not rel.parts[2].endswith("-conformance"):  # 적합성 시험 키트는 시험 코드
                scan_rust(root, path, hits)
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or path.suffix not in PATH_SUFFIXES or any(p in SKIP_DIRS for p in rel.parts):
            continue
        if path.name == Path(__file__).name:
            continue  # 이 검사의 정규식 설명
        for no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if MACHINE_PATH.search(line):
                hits.append((rel.as_posix(), "PATH", no, line.strip()[:160]))
    return hits


def counts(hits: list[tuple[str, str, int, str]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for rel, rule, _, _ in hits:
        out.setdefault(rel, {}).setdefault(rule, 0)
        out[rel][rule] += 1
    return out


def crate_of(rel: str) -> str:
    """기준을 묶는 단위: crates/<무리>/<crate> 또는 acceptance/<이름>, 그 밖은 파일 그대로."""
    parts = rel.split("/")
    if parts[0] == "crates" and len(parts) > 2:
        return "/".join(parts[:3])
    if parts[0] == "acceptance" and len(parts) > 1:
        return "/".join(parts[:2])
    return rel


def base_policy(root: Path, policy_rel: str) -> dict | None:
    """비교 기준 판(환경 변수 MOOKKO_BASELINE_REF, 없으면 foundation/engine)의 같은 정책 파일. git이나 그 판이 없으면 None."""
    ref = os.environ.get("MOOKKO_BASELINE_REF", "foundation/engine")
    try:
        out = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{policy_rel}"],
                             capture_output=True, text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except ValueError:
        return None


def ratchet_main(name: str, policy_rel: str, scan_fn, rule_text: dict[str, str]) -> int:
    """파일별 기준(baseline)을 둔 검사의 공통 판정(mookko-rust-qa 2026-11-03 래칫 지적).
    - 늘어남: crate 단위 규칙별 합계가 기준보다 많으면 **경고 모드여도 실패**(같은 crate 안에서 파일 사이로 옮긴 것은 경고).
    - 줄어듦·기한 지남: enforce면 실패, 아니면 경고.
    - 기준 파일을 손으로 늘림: 비교 기준 판의 정책 파일보다 어느 칸이든 크면 실패. 검사 자체를 고쳐 늘어난 것처럼 이유가 있으면
      정책 파일 `raised`에 파일마다 사유를 적어야 함(리뷰에 보임).
    `--write-baseline`은 기존 칸만 min(기준, 지금)으로 낮추고 새 칸은 더하지 않는다. `--init-baseline`은 기준이 비었을 때만
    지금 개수로 처음 쓴다."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    policy_path = root / policy_rel
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        enforce, baseline, expires = policy["enforce"], policy["baseline"], policy["expires"]
        expired = datetime.date.fromisoformat(expires) < datetime.date.today()
    except (OSError, ValueError, KeyError) as e:
        print(f"{policy_rel}:1: 읽지 못했습니다: {e}")
        return 1
    hits = scan_fn(root)
    found = counts(hits)
    if "--init-baseline" in flags or "--write-baseline" in flags:
        if "--init-baseline" in flags:
            if baseline and not any(a.startswith("--checker-changed=") for a in flags):
                print(f"{policy_rel}:1: 기준이 이미 있어 처음 쓰기를 하지 않습니다(--write-baseline은 낮추기만)")
                return 1
            reason = next((a.split("=", 1)[1] for a in flags if a.startswith("--checker-changed=")), "")
            if baseline and not reason:
                print(f"{policy_rel}:1: --checker-changed=<사유>가 필요합니다")
                return 1
            for rel, rules in found.items():
                if any(n > baseline.get(rel, {}).get(rule, 0) for rule, n in rules.items()) and baseline:
                    policy.setdefault("raised", {})[rel] = reason
            policy["baseline"] = found
        else:
            policy["baseline"] = {
                rel: kept for rel, rules in baseline.items()
                if (kept := {rule: min(n, found.get(rel, {}).get(rule, 0)) for rule, n in rules.items()
                             if min(n, found.get(rel, {}).get(rule, 0)) > 0})
            }
        policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        total = sum(sum(v.values()) for v in policy["baseline"].values())
        print(f"baseline을 다시 썼습니다({len(policy['baseline'])} 파일, {total} 건)")
        return 0
    if "--list" in flags:
        for rel, rule, no, text in hits:
            print(f"{rel}:{no}: [{rule}] {text}")
    hard: list[str] = []  # 늘 실패
    soft: list[str] = []  # enforce면 실패, 아니면 경고
    crate_now: dict[tuple[str, str], int] = {}
    crate_base: dict[tuple[str, str], int] = {}
    for rel, rules in found.items():
        for rule, n in rules.items():
            crate_now[(crate_of(rel), rule)] = crate_now.get((crate_of(rel), rule), 0) + n
    for rel, rules in baseline.items():
        for rule, n in rules.items():
            crate_base[(crate_of(rel), rule)] = crate_base.get((crate_of(rel), rule), 0) + n
    for rel in sorted(set(found) | set(baseline)):
        for rule in sorted(set(found.get(rel, {})) | set(baseline.get(rel, {}))):
            now, allowed = found.get(rel, {}).get(rule, 0), baseline.get(rel, {}).get(rule, 0)
            key = (crate_of(rel), rule)
            if now > allowed:
                lines = [f"{r}:{n}: {rule_text[k]} ({k}, 기준 {allowed}건, 지금 {now}건): {txt[:120]}"
                         for r, k, n, txt in hits if r == rel and k == rule]
                if crate_now.get(key, 0) > crate_base.get(key, 0):
                    hard.extend(lines)
                else:
                    soft.append(f"{rel}:1: {rule}가 {allowed}건에서 {now}건으로 늘었지만 {key[0]} 합계는 그대로입니다(옮김). 기준을 맞추세요")
            elif now < allowed:
                soft.append(f"{policy_rel}:1: {rel} {rule}가 {allowed}건에서 {now}건으로 줄었습니다. 기준을 낮추세요(--write-baseline)")
            elif now and expired:
                soft.append(f"{rel}:1: {rule} {now}건이 기한 {expires}을 넘겨 남아 있습니다. 옮기세요")
    base = base_policy(root, policy_rel)
    if base is not None:
        for rel, rules in baseline.items():
            for rule, n in rules.items():
                was = base.get("baseline", {}).get(rel, {}).get(rule, 0)
                if n > was and not str(policy.get("raised", {}).get(rel, "")).strip():
                    hard.append(f"{policy_rel}:1: {rel} {rule} 기준을 {was}건에서 {n}건으로 늘렸습니다. 기준은 늘리지 않습니다")
    for p in hard:
        print(p)
    for p in soft:
        print(p if enforce else f"경고: {p}")
    summary = ", ".join(f"{k} {sum(1 for h in hits if h[1] == k)}" for k in rule_text)
    failed = hard + (soft if enforce else [])
    if failed:
        print(f"{name} check failed ({len(failed)} problems; {summary})")
        return 1
    mode = "enforce" if enforce else "warn only"
    compared = "" if base is not None else ", 기준 판 비교 건너뜀"
    print(f"{name} check passed ({summary}; {len(soft)} warnings, baseline {len(baseline)} files, {mode}{compared})")
    return 0


def main() -> int:
    return ratchet_main("hardcoded value", "docs/policy/hardcoded-values.json", scan, RULE_TEXT)


if __name__ == "__main__":
    sys.exit(main())

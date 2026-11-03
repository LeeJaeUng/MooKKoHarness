"""개발·시험 컨테이너가 루프백에만 열리는지 검사 (CLAUDE.md › 포트 "모두 127.0.0.1에서만 엽니다", PM 2026-11-03).

WSL을 mirrored 네트워크로 바꾸면 WSL 안에서 모든 주소(0.0.0.0)에 연 포트가 PC 밖에서도 보인다. 그래서 저장소 안 셸
스크립트가 띄우는 컨테이너와 시험 설정이 루프백에만 묶이게 잡는다. 운영 실행 파일의 듣는 주소는 엔진 runtime이 켜질 때
따로 거부한다(mookko-runtime checks.rs).
- Bash(scripts/·crates/의 *.sh): podman·docker의 run·create·pod create에서
  - `-p`/`--publish` 값은 `127.0.0.1:`·`[::1]:`이나 `"$BIND_HOST` 변수(설정 json의 bindHost)로 시작해야 한다.
  - `-P`/`--publish-all`, `--network host`/`--net host`(= 붙여 쓴 것 포함)는 금지.
- JSON(dev/*.json): `bindHost`는 `127.0.0.1`이나 `::1`이어야 한다.
실패하면 `파일:줄: 이유`를 한 줄씩 내고 1로 끝난다.

사용: python3 -X utf8 ci/check-dev-exposure.py [저장소 루트]  (루트를 주면 표본 폴더를 검사할 수 있음)
"""

from __future__ import annotations

import os
import json
import re
import shlex
import sys
from pathlib import Path

SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist"}
LOOPBACK = {"127.0.0.1", "::1"}
# podman·docker·"$PODMAN" 같은 변수, sudo, `container run`, `pod create`를 모두 봅니다(QA 1c3fef2 T6).
CONTAINER_CMD = re.compile(
    r"(?:^|[\s;&|(`])(?:sudo\s+)?(?:podman|docker|\"?\$\{?[A-Za-z_][A-Za-z0-9_]*\}?\"?)\s+"
    r"(?:container\s+)?(?:run|create)\b"
    r"|\b(?:podman|docker)\s+pod\s+create\b"
)
PUBLISH_OK = re.compile(r"^(127\.0\.0\.1:|\[::1\]:|\$\{?BIND_HOST\b)")
PASTA_FORWARD = ("-t", "-u", "-T", "-U", "--tcp-ports", "--udp-ports")


def files(root: Path, base: Path, pattern: str):
    if not base.exists():
        return
    for path in sorted(base.rglob(pattern)):
        rel = path.relative_to(root)
        if path.is_file() and not any(p in SKIP_DIRS for p in rel.parts):
            yield path, rel


def logical_lines(text: str):
    """줄 끝 `\\`로 이어 쓴 명령을 한 줄로 합쳐 (시작 줄 번호, 내용)으로 낸다."""
    start, buf = 0, []
    for no, line in enumerate(text.splitlines(), 1):
        if not buf:
            start = no
        if line.rstrip().endswith("\\"):
            buf.append(line.rstrip()[:-1])
            continue
        buf.append(line)
        yield start, " ".join(buf)
        buf = []
    if buf:
        yield start, " ".join(buf)


def check_shell(rel: Path, text: str, problems: list[str]) -> None:
    for no, line in logical_lines(text):
        if line.lstrip().startswith("#") or not CONTAINER_CMD.search(line):
            continue
        where = f"{rel.as_posix()}:{no}"
        try:
            words = shlex.split(line, comments=True, posix=True)
        except ValueError:
            words = [w.strip("\"'") for w in line.split()]
        for i, word in enumerate(words):
            following = words[i + 1] if i + 1 < len(words) else ""
            value = None
            if word in ("-p", "--publish"):
                value = following
            elif word.startswith("--publish="):
                value = word.split("=", 1)[1]
            elif re.fullmatch(r"-p\S+", word):
                value = word[2:]
            elif re.fullmatch(r"-[A-Za-z]+", word) and word.endswith("p"):
                value = following
            if value is not None and not PUBLISH_OK.match(value):
                problems.append(f"{where}: 컨테이너 포트는 127.0.0.1(또는 \"$BIND_HOST\")에만 묶어야 합니다: {value}")
            if word in ("--publish-all", "--publish-all=true") or (re.fullmatch(r"-[A-Za-z]+", word) and "P" in word):
                problems.append(f"{where}: {word}(-P, --publish-all)는 모든 주소에 엽니다")
            network = None
            if word in ("--network", "--net"):
                network = following
            elif word.startswith(("--network=", "--net=")):
                network = word.split("=", 1)[1]
            if network is not None:
                if network == "host":
                    problems.append(f"{where}: 호스트 네트워크(--network host)는 쓰지 않습니다")
                elif network.startswith("pasta") and any(opt in re.split(r"[:,=\s]", network) for opt in PASTA_FORWARD):
                    problems.append(f"{where}: pasta 포트 전달 옵션은 쓰지 않습니다. -p 127.0.0.1:…을 쓰세요: {network}")


def check_json(rel: Path, text: str, problems: list[str]) -> None:
    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "bindHost" and value not in LOOPBACK:
                    problems.append(f"{rel.as_posix()}:1: bindHost는 127.0.0.1이나 ::1이어야 합니다: {value}")
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(json.loads(text))


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    problems: list[str] = []
    scanned = 0
    for base in (root / "scripts", root / "crates"):
        for path, rel in files(root, base, "*.sh"):
            scanned += 1
            check_shell(rel, path.read_text(encoding="utf-8"), problems)
    for path, rel in files(root, root / "scripts" / "dev", "*.json"):
        scanned += 1
        check_json(rel, path.read_text(encoding="utf-8"), problems)
    for p in problems:
        print(p)
    if problems:
        print(f"dev exposure check failed ({len(problems)} problems)")
        return 1
    print(f"dev exposure check passed ({scanned} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

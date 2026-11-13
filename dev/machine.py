"""이 기계에만 맞는 값 찾기 (PM 2026-11-03, 사용자 "하드코딩으로 경로같은거 들어간거 뭐야").

저장소에 커밋하는 설정(dev/*.json)에는 기계 전용 절대 경로를 두지 않는다. 경로는 본 체크아웃 기준 상대 경로로
적고, 기계마다 다른 값은 아래 순서로 찾는다.
1. 환경 변수(이름은 부르는 쪽이 정함)
2. 본 체크아웃의 data/dev-machine.json(git 제외, 모양은 config/dev/dev-machine.example.json)
3. 자동으로 찾기(PATH, 마운트 위치 등)
본 체크아웃: worktree는 늘 <본 체크아웃>/.claude/worktrees/<이름> 아래에 있으므로(CLAUDE.md) 그 위로 올라간다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def main_root(start: Path | None = None) -> Path:
    """이 저장소 본 체크아웃의 최상위 폴더. MOOKKO_MAIN_CHECKOUT이 있으면 그것(하네스 카나리처럼 /tmp 사본에서 돌아도 이 기계의
    data/dev-machine.json·가상 디스크를 보게, 백로그 8)."""
    forced = os.environ.get("MOOKKO_MAIN_CHECKOUT")
    if forced and start is None:
        return Path(forced).resolve()
    here = (start or Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".")).resolve()
    here = here if here.is_dir() else here.parent
    root = here
    while not (root / ".git").exists() and root.parent != root:
        root = root.parent
    if not (root / ".git").exists():  # git 밖(압축본 등): 받은 제품 폴더 그대로
        return here
    if root.parent.name == "worktrees" and root.parent.parent.name == ".claude":
        return root.parents[2]
    return root


def local(key: str, default: object = None) -> object:
    """data/dev-machine.json의 값(점으로 이은 키, 예: "diskGuard.hostPath"). 파일이나 키가 없으면 default."""
    path = main_root() / "data" / "dev-machine.json"
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def repo_path(value: str) -> Path:
    """설정의 경로: ~로 시작하면 사용자 집 기준, 상대 경로면 본 체크아웃 기준."""
    if value.startswith("~"):
        return Path(os.path.expanduser(value))
    path = Path(value)
    return path if path.is_absolute() else main_root() / path


def mount_point(path: Path) -> Path:
    """path가 들어 있는 파일 시스템의 마운트 위치."""
    path = path.resolve()
    while not os.path.ismount(path) and path.parent != path:
        path = path.parent
    return path

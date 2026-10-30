"""빌드 전 디스크 검사: 남은 공간이 기준 아래거나 빌드 캐시가 상한을 넘으면 빌드를 시작하지 않는다.

2026-10-30 세션마다 따로 쌓인 cargo 빌드 캐시로 WSL 가상 디스크가 189GB까지 자라 C 드라이브가 0이 되었고,
WSL이 입출력 오류로 멈춰 모든 세션의 빌드·검사가 막혔다. 같은 일이 다시 생기지 않게 check-all.sh가 맨 먼저 부른다.
기준은 scripts/dev/disk-guard.json에서만 읽는다. 지우는 일은 하지 않는다(정리는 사람이 정함, 임시 파일은 휴지통 규칙).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "scripts" / "dev" / "disk-guard.json"
GIB = 1024**3


def tree_size(base: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).lstat().st_blocks * 512
            except FileNotFoundError:
                continue  # 다른 빌드가 그 사이 지운 파일
    return total


def check(settings: dict) -> list[str]:
    problems: list[str] = []
    for item in settings["freeSpace"]:
        path = Path(item["path"])
        if not path.exists():
            continue
        free = shutil.disk_usage(path).free
        if free < item["minFreeGiB"] * GIB:
            problems.append(
                f"{item['path']}: 남은 공간 {free / GIB:.1f}GiB < 기준 {item['minFreeGiB']}GiB ({item['label']})"
            )
    cache = settings["buildCache"]
    cache_dir = Path(os.path.expanduser(cache["dir"]))
    if cache_dir.is_dir():
        sizes = sorted(((tree_size(p), p.name) for p in cache_dir.iterdir() if p.is_dir()), reverse=True)
        total = sum(size for size, _ in sizes)
        if total > cache["maxTotalGiB"] * GIB:
            top = ", ".join(f"{name} {size / GIB:.1f}GiB" for size, name in sizes[:5])
            problems.append(
                f"{cache['dir']}: 빌드 캐시 합계 {total / GIB:.1f}GiB > 상한 {cache['maxTotalGiB']}GiB (큰 것: {top})"
            )
    return problems


def main() -> int:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    problems = check(settings)
    if problems:
        print("disk guard failed (빌드를 시작하지 않습니다. 통합 담당에 알리고, 지울 것은 사용자 결정·휴지통 규칙대로):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("disk guard passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

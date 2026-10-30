"""빌드 전 디스크 검사: 빌드 캐시가 한도를 넘거나 공간이 모자라면 오래된 캐시부터 지우고, 그래도 모자라면 빌드를 막는다.

2026-10-30 세션마다 따로 쌓인 cargo 빌드 캐시로 WSL 가상 디스크가 189GB까지 자라 C 드라이브가 0이 되었고,
WSL이 입출력 오류로 멈춰 모든 세션의 빌드·검사가 막혔다. 같은 일이 다시 생기지 않게 check-all.sh가 맨 먼저 부른다.
- 캐시는 다시 만들 수 있어 휴지통 없이 지워도 된다(사용자 결정 2026-10-30). 지운 것은 기록 파일에 남긴다.
- 지금 쓰는 캐시(CARGO_TARGET_DIR)와 최근에 쓴 캐시(minIdleMinutes 안)는 지우지 않는다(다른 세션 빌드를 깨지 않게).
- 가상 디스크는 안에서 지워도 줄지 않으므로, 여유 = C 드라이브 남은 공간 + (vhdx 크기 - Linux 사용량)으로 본다.
  안쪽 빈 곳이 compactSlackGiB를 넘으면 압축(diskpart compact, 관리자)을 권한다.
기준은 scripts/dev/disk-guard.json에서만 읽는다. `--dry-run`이면 지우지 않고 무엇을 지울지만 보인다.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "scripts" / "dev" / "disk-guard.json"
GIB = 1024**3


@dataclass
class Cache:
    path: Path
    size: int
    last_used: float


def tree_size(base: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).lstat().st_blocks * 512
            except FileNotFoundError:
                continue  # 다른 빌드가 그 사이 지운 파일
    return total


def last_used(base: Path) -> float:
    """캐시 폴더와 그 아래 두 단계까지의 가장 늦은 수정 시각(cargo가 debug/·.fingerprint를 고친다)."""
    newest = base.stat().st_mtime
    for child in base.iterdir():
        try:
            newest = max(newest, child.lstat().st_mtime)
            if child.is_dir() and not child.is_symlink():
                for grand in child.iterdir():
                    newest = max(newest, grand.lstat().st_mtime)
        except FileNotFoundError:
            continue  # 다른 빌드가 그 사이 지운 항목
    return newest


def caches(cache_dir: Path) -> list[Cache]:
    if not cache_dir.is_dir():
        return []
    found = [Cache(p, tree_size(p), last_used(p)) for p in cache_dir.iterdir() if p.is_dir() and not p.is_symlink()]
    return sorted(found, key=lambda c: c.last_used)  # 오래된 것부터


def headroom(host: dict) -> tuple[int, int] | None:
    """(여유 바이트, 가상 디스크 안 빈 곳 바이트). 이 PC가 아니면(경로 없음) None."""
    host_path, vhdx = Path(host["path"]), Path(host["vhdx"])
    if not host_path.exists() or not vhdx.exists():
        return None
    linux_used = shutil.disk_usage("/").used
    slack = max(0, vhdx.stat().st_size - linux_used)
    return shutil.disk_usage(host_path).free + slack, slack


def record(log_path: Path, cache: Cache, reason: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "deleted": str(cache.path),
        "bytes": cache.size,
        "reason": reason,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def prune(settings: dict, dry_run: bool) -> list[str]:
    """한도를 넘은 만큼 오래된 캐시부터 지운다. 지운(또는 지울) 목록을 돌려준다."""
    cache_cfg = settings["buildCache"]
    cache_dir = Path(os.path.expanduser(cache_cfg["dir"]))
    log_path = Path(os.path.expanduser(cache_cfg["log"]))
    current = os.environ.get("CARGO_TARGET_DIR")
    idle_before = time.time() - cache_cfg["minIdleMinutes"] * 60
    found = caches(cache_dir)
    removable = [c for c in found if c.last_used < idle_before and (current is None or c.path != Path(current))]
    total = sum(c.size for c in found)
    room = headroom(settings["host"])
    need_room = 0 if room is None else max(0, settings["host"]["minHeadroomGiB"] * GIB - room[0])
    # 안쪽에서 지운 만큼은 가상 디스크가 다시 쓰므로, 지운 양이 곧 늘어난 여유다.
    done: list[str] = []
    for cache in removable:
        over_total = total > cache_cfg["maxTotalGiB"] * GIB
        over_dir = cache.size > cache_cfg["maxPerDirGiB"] * GIB
        if not (over_total or over_dir or need_room > 0):
            continue
        reason = "합계 한도" if over_total else ("폴더 한도" if over_dir else "여유 부족")
        done.append(f"{cache.path} {cache.size / GIB:.1f}GiB ({reason})")
        if not dry_run:
            shutil.rmtree(cache.path)
            record(log_path, cache, reason)
        total -= cache.size
        need_room = max(0, need_room - cache.size)
    return done


def check(settings: dict) -> tuple[list[str], list[str]]:
    """(막을 문제, 알림)."""
    problems: list[str] = []
    notes: list[str] = []
    host = settings["host"]
    room = headroom(host)
    if room is not None:
        free, slack = room
        if free < host["minHeadroomGiB"] * GIB:
            problems.append(f"{host['path']}: 여유 {free / GIB:.1f}GiB < 기준 {host['minHeadroomGiB']}GiB ({host['label']})")
        if slack > host["compactSlackGiB"] * GIB:
            notes.append(f"가상 디스크 안 빈 곳 {slack / GIB:.1f}GiB: 압축(WSL 끄고 diskpart compact, 관리자)을 통합 담당에 알리세요")
    linux = settings["linuxRoot"]
    if Path(linux["path"]).exists():
        free_linux = shutil.disk_usage(linux["path"]).free
        if free_linux < linux["minFreeGiB"] * GIB:
            problems.append(f"{linux['path']}: 남은 공간 {free_linux / GIB:.1f}GiB < 기준 {linux['minFreeGiB']}GiB")
    cache_cfg = settings["buildCache"]
    found = caches(Path(os.path.expanduser(cache_cfg["dir"])))
    total = sum(c.size for c in found)
    if total > cache_cfg["maxTotalGiB"] * GIB:
        top = ", ".join(f"{c.path.name} {c.size / GIB:.1f}GiB" for c in sorted(found, key=lambda c: -c.size)[:5])
        problems.append(f"{cache_cfg['dir']}: 빌드 캐시 합계 {total / GIB:.1f}GiB > 한도 {cache_cfg['maxTotalGiB']}GiB, 최근 쓴 것뿐이라 못 지움 ({top})")
    return problems, notes


def main() -> int:
    dry_run = "--dry-run" in sys.argv[1:]
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    for line in prune(settings, dry_run):
        print(f"disk guard: {'지울 것' if dry_run else '지움'} {line}")
    problems, notes = check(settings)
    for note in notes:
        print(f"disk guard: 알림 {note}")
    if problems:
        print("disk guard failed (빌드를 시작하지 않습니다. 통합 담당에 알리세요):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("disk guard passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

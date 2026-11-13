"""빌드 전 디스크 검사: 자기 캐시가 폴더 한도를 넘으면 지우고 새로 빌드하고, 공간이 모자라면 오래된 남의 캐시부터 지우고, 그래도 모자라면 빌드를 막는다.

2026-10-30 세션마다 따로 쌓인 cargo 빌드 캐시로 WSL 가상 디스크가 189GB까지 자라 C 드라이브가 0이 되었고,
WSL이 입출력 오류로 멈춰 모든 세션의 빌드·검사가 막혔다. 같은 일이 다시 생기지 않게 check-all.sh가 맨 먼저 부른다.
- 캐시는 다시 만들 수 있어 휴지통 없이 지워도 된다. 지운 것은 기록 파일에 남긴다(사용자 결정 2026-10-30).
- 자기 캐시(CARGO_TARGET_DIR)가 폴더 한도(maxPerDirGiB)를 넘으면 24시간과 상관없이 자기 캐시만 지우고 새로 빌드한다
  (사용자 결정 2026-10-30 "자기 캐시만 정리"). 다만 같은 캐시를 다른 프로세스가 쓰고 있으면 지우지 않고 막는다.
- 남의 캐시는 마지막으로 쓴 지 24시간(minIdleHours) 넘었고 돌고 있는 프로세스(/proc 환경)가 쓰지 않는 것만, 여유가
  모자랄 때 오래된 것부터 지운다. 지울 수 있는 것만으로 모자라면 하나도 지우지 않고 빌드를 막는다(사용자 결정). 합계 한도는 없다.
- 마지막 사용 시각 = 캐시 폴더의 기록 파일(stampFile, 이 검사가 지금 캐시에 매번 남김)과 폴더 아래 두 단계
  (cargo가 debug/·.fingerprint를 고침) 수정 시각 중 가장 늦은 것. check-all 없이 cargo만 돌린 빌드도 잡힌다.
- 가상 디스크는 안에서 지워도 줄지 않으므로, 여유 = C 드라이브 남은 공간 + (vhdx 크기 - Linux 사용량)으로 본다.
  안쪽 빈 곳이 compactSlackGiB를 넘으면 압축(diskpart compact, 관리자)을 권한다.
- 그와 따로 C 드라이브 실제 남은 공간이 minFreeGiB보다 적으면 막는다. 안쪽 빈 곳은 가상 디스크만 다시 쓸 수 있어서,
  Windows 쪽 다른 쓰기나 가상 디스크 메타데이터가 C 드라이브를 0으로 만드는 것은 막지 못한다(2026-11-02 여유 49.2GiB로
  셌는데 실제 C 드라이브는 0.2GB였음).
기준은 config/dev/disk-guard.json에서만 읽는다. `--dry-run`이면 지우지 않고 무엇을 지울지만 보인다.
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

SETTINGS = Path(__file__).resolve().parents[1] / "config" / "dev" / "disk-guard.json"  # 하네스 설정
sys.path.insert(0, str(Path(__file__).resolve().parent))
import machine  # noqa: E402  (같은 폴더의 도우미)
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
    """캐시 폴더와 그 아래 두 단계까지의 가장 늦은 수정 시각(기록 파일과 cargo가 고치는 debug/·.fingerprint 포함)."""
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


# 캐시를 쓰지 않는데 환경만 물려받아 오래 남는 프로세스(시험용 DB를 띄운 rootless Podman의 일시정지·감시 프로세스).
# 이것들을 '쓰는 중'으로 보면 자기 캐시가 한도를 넘어도 끝까지 못 지운다(2026-11-01 catatonit -P가 CARGO_TARGET_DIR를 물고 남음).
NOT_BUILDERS = frozenset({"catatonit", "conmon", "podman", "pasta", "pasta.avx2", "slirp4netns", "rootlessport"})


def own_lineage() -> set[str]:
    """이 검사 자신과 조상 프로세스 번호(check-all·감싸기 셸). 자기 캐시를 '남이 쓰는 중'으로 보지 않게."""
    lineage: set[str] = set()
    pid = str(os.getpid())
    while pid not in ("0", "") and pid not in lineage:
        lineage.add(pid)
        try:
            stat = (Path("/proc") / pid / "stat").read_text(encoding="utf-8")
        except OSError:
            break
        pid = stat.rsplit(")", 1)[1].split()[1]  # 이름에 공백·괄호가 있어도 ')' 뒤 두 번째 칸이 부모
    return lineage


def in_use(exclude: set[str] | None = None) -> set[Path]:
    """지금 돌고 있는 프로세스가 쓰는 캐시(/proc/*/environ의 CARGO_TARGET_DIR). 시험만 오래 돌아 새 파일이 없어도 잡는다."""
    used: set[Path] = set()
    proc = Path("/proc")
    if not proc.is_dir():
        return used
    for entry in proc.iterdir():
        if not entry.name.isdigit() or (exclude and entry.name in exclude):
            continue
        try:
            if (entry / "comm").read_text(encoding="utf-8").strip() in NOT_BUILDERS:
                continue
            environ = (entry / "environ").read_bytes()
        except OSError:
            continue  # 끝났거나 남의 프로세스
        for item in environ.split(b"\0"):
            if item.startswith(b"CARGO_TARGET_DIR="):
                target = Path(os.fsdecode(item.split(b"=", 1)[1]))
                if not target.is_absolute():
                    try:
                        target = Path(os.readlink(entry / "cwd")) / target  # 그 프로세스의 작업 폴더 기준
                    except OSError:
                        continue
                used.add(target.resolve())
    return used


def in_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False


def headroom(host: dict) -> tuple[int, int] | None:
    """(여유 바이트, 가상 디스크 안 빈 곳 바이트). 이 PC가 아니면(경로 없음) None."""
    host_path, vhdx = Path(host["path"]), Path(host["vhdx"])
    if not host_path.exists() or not vhdx.exists():
        if in_wsl():  # WSL 안인데 가상 디스크를 못 찾으면 C 드라이브 검사를 말없이 건너뛰지 않음(mookko-rust-qa 11-03)
            print(f"disk guard: 알림 가상 디스크를 찾지 못해 Windows 드라이브 남은 공간을 보지 못했습니다: {vhdx} "
                  f"(data/dev-machine.json의 diskGuard.vhdx를 확인하세요)")
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


def delete(cache: Cache, reason: str, log_path: Path, dry_run: bool, done: list[str]) -> bool:
    if not dry_run:
        try:
            shutil.rmtree(cache.path)
        except OSError as err:
            done.append(f"{cache.path} 지우지 못함: {err}")
            return False
        record(log_path, cache, reason)
    done.append(f"{cache.path} {cache.size / GIB:.1f}GiB ({reason})")
    return True


def prune(settings: dict, dry_run: bool) -> list[str]:
    """자기 캐시가 폴더 한도를 넘으면 지우고, 여유가 모자라면 24시간 넘은 남의 캐시를 오래된 것부터 지운다."""
    cache_cfg = settings["buildCache"]
    cache_dir = Path(os.path.expanduser(cache_cfg["dir"]))
    log_path = Path(os.path.expanduser(cache_cfg["log"]))
    current = os.environ.get("CARGO_TARGET_DIR")
    own_path = Path(current).resolve() if current else None
    found = caches(cache_dir)
    others_busy = in_use(exclude=own_lineage())
    done: list[str] = []
    own = next((c for c in found if own_path is not None and c.path.resolve() == own_path), None)
    if own is not None and own.size > cache_cfg["maxPerDirGiB"] * GIB and own_path not in others_busy:
        delete(own, "자기 캐시 폴더 한도", log_path, dry_run, done)
    idle_before = time.time() - cache_cfg["minIdleHours"] * 3600
    removable = [
        c for c in found
        if c is not own and c.last_used < idle_before and c.path.resolve() not in others_busy
    ]
    room = headroom(settings["host"])
    need_room = 0 if room is None else max(0, settings["host"]["minHeadroomGiB"] * GIB - room[0])
    # 지울 수 있는 것만으로 여유를 못 맞추면 하나도 지우지 않고 막는다(check가 알림, 사용자 결정).
    if need_room == 0 or sum(c.size for c in removable) < need_room:
        return done
    # 안쪽에서 지운 만큼은 가상 디스크가 다시 쓰므로, 지운 양이 곧 늘어난 여유다.
    for cache in removable:
        if need_room <= 0:
            break
        if delete(cache, "여유 부족", log_path, dry_run, done):
            need_room -= cache.size
    return done


def check(settings: dict) -> tuple[list[str], list[str]]:
    """(막을 문제, 알림)."""
    problems: list[str] = []
    notes: list[str] = []
    host = settings["host"]
    room = headroom(host)
    if room is None and in_wsl() and str(host["path"]).startswith("/mnt/") and Path(host["path"]).exists():
        # 가상 디스크를 못 찾아도 Windows 드라이브 실제 남은 공간 기준(minFreeGiB)은 본다(백로그 8). 여유(빈 곳 더한 값)는 못 셈.
        host_free = shutil.disk_usage(host["path"]).free
        if host_free < host["minFreeGiB"] * GIB:
            problems.append(f"{host['path']}: Windows 드라이브 실제 남은 공간 {host_free / GIB:.1f}GiB < 기준 {host['minFreeGiB']}GiB "
                            f"(가상 디스크를 못 찾아 여유 계산은 건너뜀; C 드라이브 비우기 필요, 사용자 결정 필요)")
    if room is not None:
        free, slack = room
        host_free = shutil.disk_usage(host["path"]).free
        if host_free < host["minFreeGiB"] * GIB:
            problems.append(
                f"{host['path']}: Windows C 드라이브 실제 남은 공간 {host_free / GIB:.1f}GiB < 기준 {host['minFreeGiB']}GiB "
                f"(가상 디스크 안 빈 곳 {slack / GIB:.1f}GiB는 C 드라이브를 지켜 주지 않음; "
                f"가상 디스크 압축(WSL 끄고 diskpart compact, 관리자)이나 C 드라이브 비우기 필요, 사용자 결정 필요)"
            )
        if free < host["minHeadroomGiB"] * GIB:
            problems.append(
                f"{host['path']}: 여유 {free / GIB:.1f}GiB < 기준 {host['minHeadroomGiB']}GiB "
                f"({host['label']}; 24시간 넘은 남의 캐시만으로 모자라 지우지 않음, 사용자 결정 필요)"
            )
        if slack > host["compactSlackGiB"] * GIB:
            notes.append(f"가상 디스크 안 빈 곳 {slack / GIB:.1f}GiB: 압축(WSL 끄고 diskpart compact, 관리자)을 통합 담당에 알리세요")
    linux = settings["linuxRoot"]
    if Path(linux["path"]).exists():
        free_linux = shutil.disk_usage(linux["path"]).free
        if free_linux < linux["minFreeGiB"] * GIB:
            problems.append(f"{linux['path']}: 남은 공간 {free_linux / GIB:.1f}GiB < 기준 {linux['minFreeGiB']}GiB")
    cache_cfg = settings["buildCache"]
    found = caches(Path(os.path.expanduser(cache_cfg["dir"])))
    # 폴더 한도: 자기 캐시는 prune이 지웠어야 한다(남아 있으면 다른 프로세스가 쓰는 중이거나 지우기 실패). 남의 캐시는 알림만.
    current = os.environ.get("CARGO_TARGET_DIR")
    current_path = Path(current).resolve() if current else None
    for c in found:
        if c.size > cache_cfg["maxPerDirGiB"] * GIB:
            line = f"{c.path}: 캐시 {c.size / GIB:.1f}GiB > 폴더 한도 {cache_cfg['maxPerDirGiB']}GiB"
            if current_path is not None and c.path.resolve() == current_path:
                problems.append(line + " (자기 캐시인데 다른 프로세스가 쓰는 중이거나 지우지 못함)")
            else:
                notes.append(line + " (그 세션이 다음 빌드 때 스스로 지움)")
    return problems, notes


def stamp(settings: dict) -> None:
    """지금 쓰는 캐시에 마지막 빌드 시각을 남긴다(24시간 판정용)."""
    current = os.environ.get("CARGO_TARGET_DIR")
    if not current:
        return
    target = Path(current)
    target.mkdir(parents=True, exist_ok=True)
    (target / settings["buildCache"]["stampFile"]).touch()


def resolve_host(host: dict) -> None:
    """기계 전용 경로를 저장소 설정에 두지 않는다(PM 2026-11-03). vhdx는 본 체크아웃 기준 상대 경로이고,
    host.path가 비었으면 그 vhdx가 든 드라이브의 마운트 위치로 본다. data/dev-machine.json의 diskGuard.vhdx·hostPath가 있으면
    그것을 쓴다(dev/machine.py)."""
    host["vhdx"] = str(machine.local("diskGuard.vhdx") or machine.repo_path(host["vhdx"]))
    host["path"] = str(machine.local("diskGuard.hostPath") or host.get("path") or machine.mount_point(Path(host["vhdx"]).parent))


def main() -> int:
    dry_run = "--dry-run" in sys.argv[1:]
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    resolve_host(settings["host"])
    if not dry_run:
        stamp(settings)
    for line in prune(settings, dry_run):
        print(f"disk guard: {'지울 것' if dry_run else '지움'} {line}")
    problems, notes = check(settings)
    for note in notes:
        print(f"disk guard: 알림 {note}")
    if problems:
        print("disk guard failed (빌드를 시작하지 않습니다. 통합 담당·PM에 알리세요):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("disk guard passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

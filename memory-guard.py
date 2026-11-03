"""PC 물리 메모리 관문(WSL 안에서 씀). 사용자 2026-11-03 "램 90%이하로 만 먹어야해"(PM 전달).

판정은 Windows 전체 사용률로 한다. WSL VM 안의 /proc/meminfo는 page cache 때문에 Windows가 보는 vmmemWSL 크기와
다르므로 판정에 쓰지 않는다(기록용으로만 봄). 설정은 scripts/dev/memory-guard.json.

  memory-guard.py slots <자리 수>
                                빌드 자리를 잡기 전. hard 이상이면 resume 미만이 될 때까지 기다린다. soft 이상이면
                                page cache를 비우고 1을, 아니면 받은 자리 수를 표준 출력에 낸다(PM 11-03: 85% 이상이면 자리 1개).
  memory-guard.py open <이름>   시험 컨테이너를 열기 전. hard 이상이면 resume 미만이 될 때까지 기다린다.
  memory-guard.py step <이름> <작업 수>
                                단계를 시작하기 전. hard 이상이면 resume 미만이 될 때까지 기다린다.
                                soft 이상이면 page cache를 비우고 줄인 작업 수를, 아니면 받은 작업 수를 표준 출력에 낸다.
  memory-guard.py watch         빌드 중 pollSeconds마다 사용률을 기록하고 soft 이상이면 page cache를 비운다.
                                부모 프로세스가 끝나거나 SIGTERM을 받으면 최고값(Windows %, WSL 사용, swap)을 내고 끝난다.
  memory-guard.py percent       지금 Windows 사용률만 낸다.
기록은 표준 오류에 `== 메모리 …` 한 줄씩 낸다. 기한(maxWaitMinutes)을 넘기면 1로 끝난다.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SETTINGS = Path(__file__).resolve().with_name("memory-guard.json")


def load() -> dict:
    # 표본 시험만 MOOKKO_MEMORY_GUARD_SETTINGS로 다른 문턱 파일을 줍니다.
    path = Path(os.environ.get("MOOKKO_MEMORY_GUARD_SETTINGS") or SETTINGS)
    return json.loads(path.read_text(encoding="utf-8"))


def log(text: str) -> None:
    print(f"== 메모리 {time.strftime('%H:%M:%S')} {text}", file=sys.stderr, flush=True)


def windows_percent(cfg: dict) -> float:
    """Windows 전체 사용률. powershell.exe가 가끔 실패하므로(2026-11-03 메모리가 찼을 때 rc=1) 세 번까지 다시 묻고,
    그래도 못 읽으면 100%로 봅니다(못 잰 채로 빌드를 늘리지 않음). 실패는 기록에 남깁니다."""
    error = ""
    for attempt in range(3):
        result = subprocess.run(
            [
                cfg["powershell"],
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$o=Get-CimInstance Win32_OperatingSystem; \"{0} {1}\" -f $o.TotalVisibleMemorySize,$o.FreePhysicalMemory",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = result.stdout.split()
        if result.returncode == 0 and len(out) == 2 and out[0].isdigit() and out[1].isdigit():
            total, free = int(out[0]), int(out[1])
            return round(100.0 * (total - free) / total, 1)
        error = f"rc={result.returncode} {result.stderr.strip()[:200]}"
        time.sleep(2 * (attempt + 1))
    log(f"Windows 사용률을 읽지 못했습니다({error}). 100%로 봅니다")
    return 100.0


def wsl_used_mib() -> tuple[int, int]:
    info: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, value = line.split(":", 1)
        info[key] = int(value.split()[0])
    used = (info["MemTotal"] - info["MemAvailable"]) // 1024
    swap = (info["SwapTotal"] - info["SwapFree"]) // 1024
    return used, swap


def drop_cache(cfg: dict) -> None:
    """WSL page cache를 비운다(root 필요라 Windows 쪽 wsl.exe로 이 배포판의 root 셸 하나만 부름)."""
    result = subprocess.run(
        [cfg["wslExe"], "-d", cfg["distro"], "-u", "root", "-e", "sh", "-c", "sync; echo 1 > /proc/sys/vm/drop_caches"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        log(f"page cache 비우기 실패(rc={result.returncode}): {result.stderr.strip()[:200]}")
    else:
        log("WSL page cache를 비웠습니다")


def wait_below(cfg: dict, name: str, limit: float, target: float) -> float:
    """사용률이 limit 이상이면 target 미만이 될 때까지 기다린다. 기다린 초를 기록하고 마지막 사용률을 돌려준다."""
    pct = windows_percent(cfg)
    if pct < limit:
        return pct
    start = time.monotonic()
    deadline = start + cfg["maxWaitMinutes"] * 60
    log(f"{name}: {pct}% ≥ {limit}%라 {target}% 아래까지 새로 시작하지 않고 기다립니다")
    drop_cache(cfg)
    while True:
        pct = windows_percent(cfg)
        if pct < target:
            log(f"{name}: 기다림 끝 {int(time.monotonic() - start)}초, {pct}%")
            return pct
        if time.monotonic() >= deadline:
            log(f"{name}: {cfg['maxWaitMinutes']}분을 기다려도 {pct}%라 멈춥니다. 다른 큰 프로그램을 줄이세요")
            sys.exit(1)
        time.sleep(cfg["pollSeconds"])


def cmd_open(cfg: dict, name: str) -> None:
    pct = wait_below(cfg, name, cfg["hardPercent"], cfg["resumePercent"])
    if pct >= cfg["softPercent"]:
        drop_cache(cfg)
    log(f"{name}: {pct}%, 엽니다")


def cmd_slots(cfg: dict, count: int) -> None:
    pct = wait_below(cfg, "빌드 자리", cfg["hardPercent"], cfg["resumePercent"])
    if pct >= cfg["softPercent"] and count > 1:
        drop_cache(cfg)
        log(f"빌드 자리: {pct}% ≥ {cfg['softPercent']}%라 자리 1개만 씁니다")
        count = 1
    print(count)


def cmd_step(cfg: dict, name: str, jobs: int) -> None:
    pct = wait_below(cfg, name, cfg["hardPercent"], cfg["resumePercent"])
    if pct >= cfg["softPercent"]:
        drop_cache(cfg)
        jobs = min(jobs, cfg["reducedJobs"])
        log(f"{name}: {pct}% ≥ {cfg['softPercent']}%라 작업 수를 {jobs}로 줄입니다")
    print(jobs)


def cmd_watch(cfg: dict) -> None:
    parent = os.getppid()
    peak = {"win": 0.0, "used": 0, "swap": 0}
    stop = False

    def finish(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, finish)
    while not stop and os.getppid() == parent:
        pct = windows_percent(cfg)
        used, swap = wsl_used_mib()
        peak["win"] = max(peak["win"], pct)
        peak["used"] = max(peak["used"], used)
        peak["swap"] = max(peak["swap"], swap)
        log(f"Windows {pct}%, WSL 사용 {used} MiB, swap {swap} MiB")
        if pct >= cfg["softPercent"]:
            drop_cache(cfg)
        for _ in range(int(cfg["pollSeconds"])):
            if stop or os.getppid() != parent:
                break
            time.sleep(1)
    log(f"최고: Windows {peak['win']}%, WSL 사용 {peak['used']} MiB, swap {peak['swap']} MiB")


def main() -> int:
    cfg = load()
    args = sys.argv[1:]
    if args[:1] == ["slots"] and len(args) == 2:
        cmd_slots(cfg, int(args[1]))
    elif args[:1] == ["open"] and len(args) == 2:
        cmd_open(cfg, args[1])
    elif args[:1] == ["step"] and len(args) == 3:
        cmd_step(cfg, args[1], int(args[2]))
    elif args == ["watch"]:
        cmd_watch(cfg)
    elif args == ["percent"]:
        print(windows_percent(cfg))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

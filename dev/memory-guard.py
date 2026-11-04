"""PC 물리 메모리 비상 관문(WSL 안에서 씀). PM 결정 2026-11-04(사용자 "알아서 판단좀해"): MooKKoRust 사용량은 자기 몫
(WSL 상한 6GB, 빌드 자리 1개)으로 묶고, PC 전체 사용률은 비상일 때만 본다. 옛 85%·90% 문턱과 180분 대기-실패는 없앴다.

판정 기준(설정 source): WSL 안이면 Windows 전체 사용률로 한다. WSL VM 안의 /proc/meminfo는 page cache 때문에
Windows가 보는 vmmemWSL 크기와 다르므로 판정에 쓰지 않는다(기록용으로만 봄). WSL이 아닌 Linux(내부 시험 서버,
deploy-containers §11)이면 그 기계의 /proc/meminfo(MemAvailable)로 한다. 설정은 config/dev/memory-guard.json.
powershell.exe·wsl.exe 위치는 기계마다 달라 저장소에 적지 않는다: 환경 변수 MOOKKO_POWERSHELL·MOOKKO_WSL_EXE →
data/dev-machine.json의 memoryGuard.powershell·wslExe → PATH → /mnt/<드라이브>/ 아래 Windows 기본 위치 순으로 찾는다
(dev/machine.py, PM 2026-11-03 "하드코딩으로 경로같은거").

비상 기다림: emergencyPercent 이상이면 page cache를 비우고 resumePercent 미만이 될 때까지 새로 시작하지 않는다.
maxWaitMinutes를 넘겨도 안 내려가면 기록을 남기고 그대로 진행한다(빌드 자리 1개라 더 줄일 것이 없음, 실패로 끝내지 않음).
maxWaitMinutes는 한 실행(MOOKKO_RUN_ID, dev/build-slot-acquire.sh가 정함) 전체의 몫이다. 자리 대기·시험 컨테이너·단계마다 부르므로
부를 때마다 새로 세면 몇 시간이 쌓인다(mookko-rust-qa 추가 6 ⑥). 실행별 기다린 초는 runStateFile에 두고 하루 지난 줄은 덮어쓸 때 뺀다.

  memory-guard.py slots <자리 수>
                                빌드 자리를 잡기 전. 비상 기다림 뒤 받은 자리 수를 그대로 표준 출력에 낸다.
  memory-guard.py open <이름>   시험 컨테이너를 열기 전. 비상 기다림.
  memory-guard.py step <이름> <작업 수>
                                단계를 시작하기 전. 비상 기다림 뒤 받은 작업 수를 그대로 표준 출력에 낸다.
  memory-guard.py watch         빌드 중 pollSeconds마다 사용률을 기록하고 emergency 이상이면 page cache를 비운다.
                                부모 프로세스가 끝나거나 SIGTERM을 받으면 최고값(Windows %, WSL 사용, swap)을 내고 끝난다.
  memory-guard.py percent       지금 사용률만 낸다(WSL이면 Windows 전체, 아니면 이 기계).
기록은 표준 오류에 `== 메모리 …` 한 줄씩 낸다.
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import machine  # noqa: E402  (같은 폴더의 도우미)

SETTINGS = Path(__file__).resolve().parents[1] / "config" / "dev" / "memory-guard.json"


def load() -> dict:
    # 표본 시험만 MOOKKO_MEMORY_GUARD_SETTINGS로 다른 문턱 파일을 줍니다.
    path = Path(os.environ.get("MOOKKO_MEMORY_GUARD_SETTINGS") or SETTINGS)
    return json.loads(path.read_text(encoding="utf-8"))


def log(text: str) -> None:
    print(f"== 메모리 {time.strftime('%H:%M:%S')} {text}", file=sys.stderr, flush=True)


def in_wsl() -> bool:
    """WSL 안인지. /proc/version을 못 읽어도 WSL 표지(환경 변수·interop)가 있으면 WSL로 본다(닫힌 쪽: Windows 판정)."""
    if os.environ.get("WSL_DISTRO_NAME") or Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists():
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False


def source(cfg: dict) -> str:
    """판정 기준: windows(WSL 안에서 Windows 전체) 또는 linux(이 기계). auto면 WSL인지로 고른다."""
    value = cfg.get("source", "auto")
    if value == "auto":
        return "windows" if in_wsl() else "linux"
    return value


def windows_exe(cfg: dict, key: str, env: str) -> str:
    """powershell.exe·wsl.exe 경로. 못 찾으면 이름만 돌려줘 실행 실패 → 기록에 남게 한다."""
    name = cfg["windowsExe"][key]["name"]
    found = os.environ.get(env) or machine.local(f"memoryGuard.{key}") or shutil.which(name)
    if found:
        return str(found)
    for drive in sorted(Path("/mnt").glob("?")):
        candidate = drive / cfg["windowsExe"][key]["underDrive"]
        if candidate.exists():
            return str(candidate)
    return name


def used_percent(cfg: dict) -> float:
    if source(cfg) == "linux":
        info = meminfo()
        return round(100.0 * (info["MemTotal"] - info["MemAvailable"]) / info["MemTotal"], 1)
    return windows_percent(cfg)


def meminfo() -> dict[str, int]:
    info: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, value = line.split(":", 1)
        info[key] = int(value.split()[0])
    return info


def windows_percent(cfg: dict) -> float:
    """Windows 전체 사용률. powershell.exe가 가끔 실패하므로(2026-11-03 메모리가 찼을 때 rc=1) 세 번까지 다시 묻고,
    그래도 못 읽으면 100%로 봅니다(못 잰 채로 빌드를 늘리지 않음). 실패는 기록에 남깁니다."""
    error = ""
    for attempt in range(3):
        try:
            result = subprocess.run(
                [
                    windows_exe(cfg, "powershell", "MOOKKO_POWERSHELL"),
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "$o=Get-CimInstance Win32_OperatingSystem; \"{0} {1}\" -f $o.TotalVisibleMemorySize,$o.FreePhysicalMemory",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as e:  # 실행 파일 없음·시간 초과도 못 읽은 것으로(mookko-rust-qa 11-03)
            error = f"{type(e).__name__}: {e}"
            time.sleep(2 * (attempt + 1))
            continue
        out = result.stdout.split()
        if result.returncode == 0 and len(out) == 2 and out[0].isdigit() and out[1].isdigit():
            total, free = int(out[0]), int(out[1])
            return round(100.0 * (total - free) / total, 1)
        error = f"rc={result.returncode} {result.stderr.strip()[:200]}"
        time.sleep(2 * (attempt + 1))
    log(f"Windows 사용률을 읽지 못했습니다({error}). 100%로 봅니다")
    return 100.0


def wsl_used_mib() -> tuple[int, int]:
    info = meminfo()
    used = (info["MemTotal"] - info["MemAvailable"]) // 1024
    swap = (info["SwapTotal"] - info["SwapFree"]) // 1024
    return used, swap


def drop_cache(cfg: dict) -> None:
    """WSL page cache를 비운다(root 필요라 Windows 쪽 wsl.exe로 이 배포판의 root 셸 하나만 부름).
    여러 실행이 단계마다 부르므로 dropCacheMinSeconds 안에 다시 부르면 건너뛴다(QA 1c3fef2: 1초마다 26번 비움).
    WSL이 아닌 기계(내부 시험 서버)에서는 root가 없고 다른 일과 함께 쓰므로 비우지 않는다."""
    if source(cfg) != "windows":
        return
    stamp = Path(os.path.expanduser(cfg["dropCacheStamp"]))
    try:
        if time.time() - stamp.stat().st_mtime < cfg["dropCacheMinSeconds"]:
            return
    except FileNotFoundError:
        pass
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.touch()
    try:
        result = subprocess.run(
            [windows_exe(cfg, "wslExe", "MOOKKO_WSL_EXE"), "-d", cfg["distro"], "-u", "root", "-e", "sh", "-c", "sync; echo 1 > /proc/sys/vm/drop_caches"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f"page cache 비우기 실패({type(e).__name__}: {e})")
        return
    if result.returncode != 0:
        log(f"page cache 비우기 실패(rc={result.returncode}): {result.stderr.strip()[:200]}")
    else:
        log("WSL page cache를 비웠습니다")


def run_waited(cfg: dict, add: float = 0.0) -> float:
    """이 실행(MOOKKO_RUN_ID)이 지금까지 비상으로 기다린 초. add를 더해 적는다. 실행 id가 없으면 부를 때마다 0부터."""
    run = os.environ.get("MOOKKO_RUN_ID")
    if not run:
        return 0.0
    path = Path(os.path.expanduser(cfg["runStateFile"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        try:
            state = json.loads(f.read() or "{}")
        except ValueError:
            state = {}  # 깨진 기록은 버리고 새로 씀(기다림이 더 길어지는 쪽이라 닫힌 쪽)
        now = time.time()
        state = {k: v for k, v in state.items() if now - v[1] < 86400}
        waited = state.get(run, [0.0, now])[0] + add
        if add:
            state[run] = [waited, now]
            f.seek(0)
            f.truncate()
            f.write(json.dumps(state))
        return waited


def wait_emergency(cfg: dict, name: str) -> float:
    """사용률이 emergencyPercent 이상이면 resumePercent 미만이 될 때까지 기다린다. 이 실행의 기다림이 maxWaitMinutes를 넘기면
    기록을 남기고 그대로 진행한다(PM 11-04: 기다리다 실패로 끝내지 않음). 마지막 사용률을 돌려준다."""
    pct = used_percent(cfg)
    if pct < cfg["emergencyPercent"]:
        return pct
    budget = cfg["maxWaitMinutes"] * 60 - run_waited(cfg)
    if budget <= 0:
        log(f"{name}: {pct}% ≥ 비상 {cfg['emergencyPercent']}%지만 이 실행의 기다림 {cfg['maxWaitMinutes']}분을 다 써서 그대로 진행합니다")
        return pct
    start = time.monotonic()
    log(f"{name}: {pct}% ≥ 비상 {cfg['emergencyPercent']}%라 {cfg['resumePercent']}% 아래까지 새로 시작하지 않고 기다립니다"
        f"(이 실행에 남은 기다림 {int(budget)}초)")
    drop_cache(cfg)
    try:
        while True:
            pct = used_percent(cfg)
            if pct < cfg["resumePercent"]:
                log(f"{name}: 기다림 끝 {int(time.monotonic() - start)}초, {pct}%")
                return pct
            if time.monotonic() - start >= budget:
                log(f"{name}: 이 실행에서 {cfg['maxWaitMinutes']}분을 기다려도 {pct}%라 그대로 진행합니다(빌드 자리 1개, MooKKoRust 몫 안)")
                return pct
            time.sleep(min(cfg["pollSeconds"], max(1.0, budget - (time.monotonic() - start))))
    finally:
        run_waited(cfg, time.monotonic() - start)


def cmd_open(cfg: dict, name: str) -> None:
    pct = wait_emergency(cfg, name)
    log(f"{name}: {pct}%, 엽니다")


def cmd_slots(cfg: dict, count: int) -> None:
    wait_emergency(cfg, "빌드 자리")
    print(count)


def cmd_step(cfg: dict, name: str, jobs: int) -> None:
    wait_emergency(cfg, name)
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
        pct = used_percent(cfg)
        used, swap = wsl_used_mib()
        peak["win"] = max(peak["win"], pct)
        peak["used"] = max(peak["used"], used)
        peak["swap"] = max(peak["swap"], swap)
        log(f"Windows {pct}%, WSL 사용 {used} MiB, swap {swap} MiB")
        if pct >= cfg["emergencyPercent"]:
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
        print(used_percent(cfg))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

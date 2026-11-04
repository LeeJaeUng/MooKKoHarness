"""빌드 자리 감시(Linux, MooKKo-Linux 안에서). PM 지시 2026-11-04(사용자 "그렇게해"): 그날 멈춘 check-all의 시험 컨테이너가 자리 잠금
fd를 물려받아 3시간 10분 자리를 쥔 사고가 다시 생기지 않게 한다.

  build-slot-watch.py check    자리를 기다리는 실행이 기다리는 동안 부른다(dev/build-slot-acquire.sh). 정상이면 아무것도 내지 않는다.
  build-slot-watch.py status   자리마다 쥔 프로세스·진행 기록 나이를 낸다.

판정(자리마다):
- 쥔 프로세스에 실행 입구(ci/check-all.sh·dev/with-build-slot.sh·dev/build-slots.sh)가 하나도 없으면 "주인 없는 잠금"이다.
  쥔 것이 시험 컨테이너의 conmon이고, 그 이름이 `mookko-test-<종류>-<시각>-<pid>`이며 그 pid(컨테이너를 띄운 감싸개)가 이미 없으면,
  그 컨테이너 하나만 `podman stop`해 자리를 푼다(--rm이라 지워짐). 그 밖의 프로세스는 멈추지 않고 경보만 낸다. 넓은 pkill·prune 없음.
- 실행 입구가 있는데 진행 기록(heartbeat-<자리>, memory-guard watch가 pollSeconds마다 고침)이 stallMinutes보다 오래되면 경보만 낸다.
경보는 부른 쪽 표준 오류의 `== 빌드 자리 경보 …` 줄과 <dir>/watch.log에 남긴다(Windows 알림 없음). 같은 경보는 stallMinutes마다 한 번.
설정은 config/dev/build-slots.json(dir·count·stallMinutes). podman 실행 파일은 MOOKKO_PODMAN(표본 시험용)이 있으면 그것.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SETTINGS = Path(__file__).resolve().parents[1] / "config" / "dev" / "build-slots.json"
RUNNERS = ("ci/check-all.sh", "dev/with-build-slot.sh", "dev/build-slots.sh")
TEST_CONTAINER = re.compile(r"^mookko-test-[a-z]+-\d{14}-(\d+)$")


def load() -> dict:
    path = Path(os.environ.get("MOOKKO_BUILD_SLOTS_SETTINGS") or SETTINGS)  # 표본 시험만 다른 설정
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["dir"] = Path(os.path.expanduser(cfg["dir"]))
    return cfg


def cmdline(pid: str) -> list[str]:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace").split("\0")[:-1]
    except OSError:
        return []


def comm(pid: str) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def holders(lock: Path) -> list[str]:
    """그 잠금 파일을 연 프로세스(fd가 그 파일을 가리킴)."""
    target = str(lock)
    found = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            fds = list((proc / "fd").iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                if os.readlink(fd) == target:
                    found.append(proc.name)
                    break
            except OSError:
                continue
    return found


def is_runner(pid: str) -> bool:
    return any(arg.endswith(RUNNERS) for arg in cmdline(pid))


def conmon_container(pid: str) -> tuple[str, str] | None:
    """conmon 인자에서 (컨테이너 이름, id). conmon이 아니면 None."""
    if comm(pid) != "conmon":
        return None
    args = cmdline(pid)
    name = cid = ""
    for i, arg in enumerate(args[:-1]):
        if arg in ("-n", "--name"):
            name = args[i + 1]
        elif arg in ("-c", "--cid"):
            cid = args[i + 1]
    return (name, cid) if name and cid else None


def log(cfg: dict, text: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}"
    print(f"== 빌드 자리 경보 {line}", file=sys.stderr, flush=True)
    with open(cfg["dir"] / "watch.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def due(cfg: dict, key: str) -> bool:
    """같은 경보는 stallMinutes마다 한 번만(상태 파일은 지우지 않고 덮어씀)."""
    path = cfg["dir"] / "watch-state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    now = time.time()
    if now - state.get(key, 0) < cfg["stallMinutes"] * 60:
        return False
    state[key] = now
    path.write_text(json.dumps(state), encoding="utf-8")
    return True


def check_slot(cfg: dict, slot: int, act: bool) -> list[str]:
    lock = cfg["dir"] / f"slot-{slot}"
    pids = holders(lock)
    if not pids:
        return [f"자리 {slot}: 빔"]
    runners = [p for p in pids if is_runner(p)]
    heartbeat = cfg["dir"] / f"heartbeat-{slot}"
    try:
        age = int((time.time() - heartbeat.stat().st_mtime) / 60)
    except OSError:
        age = -1
    report = [f"자리 {slot}: 쥔 프로세스 {' '.join(f'{p}({comm(p)})' for p in pids)}, 진행 기록 {age if age >= 0 else '없음'}분 전"]
    if runners:
        if age >= cfg["stallMinutes"] and act and due(cfg, f"stall-{slot}"):
            log(cfg, f"자리 {slot}: 실행 {','.join(runners)}가 진행 기록 없이 {age}분(기준 {cfg['stallMinutes']}분) — 멈추지 않음, 그 실행 담당이 확인")
        return report
    # 주인 없는 잠금: 죽은 감싸개가 남긴 시험 컨테이너만 멈춤
    others = []
    for pid in pids:
        container = conmon_container(pid)
        if container is None:
            others.append(pid)
            continue
        name, cid = container
        m = TEST_CONTAINER.match(name)
        if not m or Path(f"/proc/{m.group(1)}").exists():
            others.append(pid)
            continue
        if act:
            podman = os.environ.get("MOOKKO_PODMAN") or "podman"
            result = subprocess.run([podman, "stop", "-t", "10", cid], capture_output=True, text=True)
            log(cfg, f"자리 {slot}: 주인 없는 잠금 — 감싸개 {m.group(1)}가 없는 시험 컨테이너 {name}({cid[:12]})를 멈춤 rc={result.returncode} "
                     f"{result.stderr.strip()[:200]}")
    leftover = [p for p in others if comm(p) not in ("rootlessport", "rootlessport-child", "slirp4netns")]
    if leftover and act and due(cfg, f"orphan-{slot}"):
        log(cfg, f"자리 {slot}: 실행 입구 없이 잠금을 쥔 프로세스 {' '.join(f'{p}({comm(p)})' for p in leftover)} — 멈추지 않음, 통합 담당이 확인")
    return report


def main(argv: list[str]) -> int:
    if argv not in (["check"], ["status"]):
        print(__doc__, file=sys.stderr)
        return 2
    cfg = load()
    cfg["dir"].mkdir(parents=True, exist_ok=True)
    for slot in range(1, int(cfg["count"]) + 1):
        lines = check_slot(cfg, slot, act=argv == ["check"])
        if argv == ["status"]:
            print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

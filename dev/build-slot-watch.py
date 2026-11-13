"""빌드 자리 감시(Linux, MooKKo-Linux 안에서). PM 지시 2026-11-04(사용자 "그렇게해"): 그날 멈춘 check-all의 시험 컨테이너가 자리 잠금
fd를 물려받아 3시간 10분 자리를 쥔 사고가 다시 생기지 않게 한다.

  build-slot-watch.py check    자리를 기다리는 실행이 기다리는 동안 부른다(dev/build-slot-acquire.sh). 정상이면 아무것도 내지 않는다.
  build-slot-watch.py status   자리마다 쥔 프로세스·진행 기록 나이를 낸다.

판정(자리마다):
- 쥔 프로세스에 실행 입구(ci/check-all.sh·dev/with-build-slot.sh·dev/build-slots.sh)가 하나도 없으면 "주인 없는 잠금"이다.
  쥔 것이 시험 컨테이너의 conmon이고, 그 이름이 `mookko-test-<종류>-<시각>-<pid>`이며 그 pid(컨테이너를 띄운 감싸개)가 이미 없으면,
  그 컨테이너 하나만 `podman stop`해 자리를 푼다(--rm이라 지워짐). 그 밖의 프로세스는 멈추지 않고 경보만 낸다. 넓은 pkill·prune 없음.
- 실행 입구가 있는데 단계 진행 기록(progress-<자리>, check-all run()이 단계 시작·끝에 고침)이 stepStallMinutes보다 오래되면 경보만 낸다
  (rust-qa 11-13: 살아 있음 표시 heartbeat-<자리>는 memory-guard watch가 poll마다 고쳐 교착을 못 잡음). progress가 없으면(옛 판 하네스)
  heartbeat를 stallMinutes로 본다.
- 주인 없는 잠금에서 멈춘 컨테이너가 없는데 잠금을 쥔 프로세스가 남으면 종류(rootlessport·slirp4netns 포함)와 상관없이 경보(rust-qa 11-13 ②).
경보는 부른 쪽 표준 오류의 `== 빌드 자리 경보 …` 줄, <dir>/watch.log, 그리고 MOOKKO_SLOT_ALERT_FILE(자리 잡기가 제품 본 체크아웃
data/build-slot-alerts.log로 정함 — Windows 쪽 세션이 읽는 곳, rust-qa 11-13 ③)에 남긴다(Windows 알림 없음). 같은 경보는 stallMinutes마다 한 번.
status는 쥔 프로세스마다 pid·이름·cwd·시작 시각을 낸다(기다리는 쪽이 처음 기다릴 때 한 번 찍음).
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


def started(pid: str) -> str:
    """프로세스 시작 시각(부팅 뒤 clock tick → 지금 시각 기준으로 셈)."""
    try:
        ticks = int(Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[19])
        uptime = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - uptime + ticks / os.sysconf("SC_CLK_TCK")))
    except (OSError, ValueError, IndexError):
        return "?"


def describe(pid: str) -> str:
    try:
        cwd = os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        cwd = "?"
    return f"{pid}({comm(pid)}) cwd={cwd} 시작={started(pid)}"


def log(cfg: dict, text: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}"
    print(f"== 빌드 자리 경보 {line}", file=sys.stderr, flush=True)
    targets = [cfg["dir"] / "watch.log"]
    if os.environ.get("MOOKKO_SLOT_ALERT_FILE"):
        targets.append(Path(os.environ["MOOKKO_SLOT_ALERT_FILE"]))
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as error:
            print(f"== 빌드 자리 경보를 {target}에 쓰지 못함: {error}", file=sys.stderr, flush=True)


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

    def minutes(path: Path) -> int:
        try:
            return int((time.time() - path.stat().st_mtime) / 60)
        except OSError:
            return -1

    beat = minutes(cfg["dir"] / f"heartbeat-{slot}")
    step = minutes(cfg["dir"] / f"progress-{slot}")
    # 단계 진행 기록이 있으면 그것으로(교착도 잡음), 없으면(옛 판 하네스) 살아 있음 표시로 본다.
    if step >= 0:
        age, limit, what = step, int(cfg.get("stepStallMinutes", 60)), "단계 진행 기록"
    else:
        age, limit, what = beat, int(cfg["stallMinutes"]), "진행 기록"
    report = [f"자리 {slot}: 쥔 프로세스 {', '.join(describe(p) for p in pids)}; 살아 있음 {beat if beat >= 0 else '없음'}분 전, "
              f"단계 진행 {step if step >= 0 else '없음'}분 전"]
    if runners:
        if age >= limit and act and due(cfg, f"stall-{slot}"):
            log(cfg, f"자리 {slot}: 실행 {','.join(runners)}가 {what} 없이 {age}분(기준 {limit}분) — 멈추지 않음, 그 실행 담당이 확인 "
                     f"[{', '.join(describe(p) for p in runners)}]")
        return report
    # 주인 없는 잠금: 죽은 감싸개가 남긴 시험 컨테이너만 멈춤
    others = []
    stopped_any = False
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
            stopped_any = True
            podman = os.environ.get("MOOKKO_PODMAN") or "podman"
            result = subprocess.run([podman, "stop", "-t", "10", cid], capture_output=True, text=True)
            log(cfg, f"자리 {slot}: 주인 없는 잠금 — 감싸개 {m.group(1)}가 없는 시험 컨테이너 {name}({cid[:12]})를 멈춤 rc={result.returncode} "
                     f"{result.stderr.strip()[:200]}")
    # 방금 컨테이너를 멈췄으면 그 rootlessport·slirp4netns는 곧 함께 끝나므로 이번에는 경보하지 않는다. 멈춘 것이 없는데 남은 것은
    # 종류와 상관없이 경보(conmon이 죽고 rootlessport·slirp4netns만 잠금을 쥔 경우, rust-qa 11-13 ②).
    if others and not stopped_any and act and due(cfg, f"orphan-{slot}"):
        log(cfg, f"자리 {slot}: 실행 입구 없이 잠금을 쥔 프로세스 {', '.join(describe(p) for p in others)} — 멈추지 않음, 통합 담당이 확인")
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

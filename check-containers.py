"""컨테이너 보안 기준 검사 (docs/architecture/deploy-containers.md §3, 사용자 결정 2026-11-03 "운영은 Docker").

저장소 안 Dockerfile(Dockerfile, Dockerfile.*, *.Dockerfile)과 Compose 파일(compose*.y(a)ml, docker-compose*.y(a)ml)을 본다.
- Dockerfile
  - 모든 FROM은 다이제스트(@sha256:…)로 고정. `:latest` 금지(빌드 단계 별칭을 FROM으로 다시 쓰는 것은 됨).
  - 마지막 단계의 마지막 USER는 0이 아닌 숫자 UID(이름이나 root 금지).
  - ENV·ARG에 비밀값처럼 보이는 이름(PASSWORD·SECRET·TOKEN·PRIVATE_KEY·API_KEY) 금지(비밀값은 읽기 전용 파일로).
  - ADD로 원격 URL 받기 금지.
- Compose 서비스마다
  - 있어야 함: read_only: true, cap_drop에 ALL, security_opt에 no-new-privileges:true, 메모리 상한(mem_limit 또는
    deploy.resources.limits.memory), pids_limit, user(0·root 아님)
  - 금지: privileged: true, network_mode: host, pid: host, ipc: host, devices, docker.sock 마운트, seccomp:unconfined,
    cap_add, 다이제스트 없는 image
  - ports: 묶는 주소가 사설·루프백(10., 172.16~31., 192.168., 127.)이거나 변수(${…})여야 함. 주소 없는 포트·0.0.0.0 금지.
- Kubernetes 매니페스트(apiVersion·kind가 맨 앞 칸에 있는 *.y(a)ml, `---`로 나눈 문서마다, §3)
  - 워크로드(Deployment·StatefulSet·DaemonSet·Job·CronJob·Pod): runAsNonRoot: true, allowPrivilegeEscalation: false,
    readOnlyRootFilesystem: true, capabilities.drop [ALL], seccompProfile RuntimeDefault, automountServiceAccountToken: false
    (Kubernetes API를 부르는 운영툴 배포기만 주석 `mookko.dev/kubernetes-api-client: "true"`로 예외)
  - 워크로드 금지: privileged·hostNetwork·hostPID·hostIPC: true, hostPath, capabilities.add, runAsUser 0, Unconfined, secretKeyRef
    (비밀값은 읽기 전용 파일로)
  - 컨테이너마다: image 다이제스트 고정, resources.requests·limits의 cpu·memory. 오래 도는 것(Deployment·StatefulSet·
    DaemonSet)의 containers는 readinessProbe·livenessProbe도
  - Service: type NodePort·LoadBalancer 금지(바깥은 라우터·Gateway만)
  - Namespace: 라벨 pod-security.kubernetes.io/enforce: restricted, 같은 저장소에 그 네임스페이스의 기본 차단
    NetworkPolicy(podSelector: {}, policyTypes에 Ingress·Egress, 허용 규칙 없음)
  - PersistentVolume은 persistentVolumeReclaimPolicy: Retain, StorageClass는 reclaimPolicy: Retain(DB PV를 지워도 데이터가
    남게, deploy-containers.md §7′. 칸이 없으면 기본값 Delete라 실패)
YAML 해석기 없이 들여쓰기로만 읽는다(표준 라이브러리만, tools.md). 실패하면 `파일:줄: 이유`를 한 줄씩 내고 1로 끝난다.

사용: python3 -X utf8 scripts/ci/check-containers.py [저장소 루트]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist"}
SECRET_NAME = re.compile(r"(PASSWORD|SECRET|TOKEN|PRIVATE_KEY|API_KEY)", re.IGNORECASE)
PRIVATE_BIND = re.compile(r"^(\$\{[^}]+\}|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+|127\.\d+\.\d+\.\d+|\[::1\]):")


def files(root: Path):
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or any(p in SKIP_DIRS for p in rel.parts):
            continue
        name = path.name
        if name.endswith(".txt"):
            continue  # 하네스 표본(scripts/ci/fixtures, 이름 끝 .txt)은 실제 설정이 아님
        if name == "Dockerfile" or name.startswith("Dockerfile.") or name.endswith(".Dockerfile"):
            yield "dockerfile", path, rel
        elif re.fullmatch(r"(docker-)?compose[\w.-]*\.ya?ml", name):
            yield "compose", path, rel
        elif name.endswith((".yaml", ".yml")):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^apiVersion:", text, re.MULTILINE) and re.search(r"^kind:", text, re.MULTILINE):
                yield "kubernetes", path, rel


def check_dockerfile(rel: str, text: str, problems: list[str]) -> None:
    stages: list[str] = []
    last_stage_users: list[tuple[int, str]] = []
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        word, _, rest = line.partition(" ")
        word = word.upper()
        if word == "FROM":
            parts = rest.split()
            image = next((p for p in parts if not p.startswith("--")), "")
            alias = parts[parts.index("AS") + 1] if "AS" in parts else parts[parts.index("as") + 1] if "as" in parts else None
            if image not in stages and "@sha256:" not in image:
                problems.append(f"{rel}:{no}: FROM {image}는 다이제스트(@sha256:…)로 고정해야 합니다")
            if image.endswith(":latest"):
                problems.append(f"{rel}:{no}: :latest 이미지는 쓰지 않습니다")
            if alias:
                stages.append(alias)
            last_stage_users = []
        elif word == "USER":
            last_stage_users.append((no, rest.strip()))
        elif word in ("ENV", "ARG"):
            name = rest.split("=", 1)[0].split()[0] if rest else ""
            if SECRET_NAME.search(name):
                problems.append(f"{rel}:{no}: {word} {name}: 비밀값은 이미지에 넣지 않고 읽기 전용 파일로 줍니다")
        elif word == "ADD" and re.search(r"\bhttps?://", rest):
            problems.append(f"{rel}:{no}: ADD로 원격 URL을 받지 않습니다(고정·확인한 파일을 COPY)")
    if not last_stage_users:
        problems.append(f"{rel}:1: 마지막 단계에 USER(0이 아닌 숫자 UID)가 없습니다")
    else:
        no, user = last_stage_users[-1]
        uid = user.split(":", 1)[0]
        if not uid.isdigit() or int(uid) == 0:
            problems.append(f"{rel}:{no}: 마지막 USER {user}는 0이 아닌 숫자 UID여야 합니다")


def service_blocks(lines: list[str]):
    """services: 아래 서비스마다 (시작 줄 번호, 이름, 줄 목록)."""
    in_services = False
    svc_indent = None
    current: tuple[int, str, list[tuple[int, str]]] | None = None
    for no, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            if current:
                yield current
                current = None
            in_services = line.rstrip().startswith("services:")
            svc_indent = None
            continue
        if not in_services:
            continue
        if svc_indent is None:
            svc_indent = indent
        if indent == svc_indent and line.rstrip().endswith(":"):
            if current:
                yield current
            current = (no, line.strip()[:-1], [])
        elif current:
            current[2].append((no, line))
    if current:
        yield current


def check_compose(rel: str, text: str, problems: list[str]) -> None:
    for start, name, body in service_blocks(text.splitlines()):
        joined = "\n".join(l for _, l in body)
        where = f"{rel}:{start}"
        need = [
            (r"^\s*read_only:\s*true\b", "read_only: true"),
            (r"^\s*cap_drop:\s*(\[\s*\"?ALL\"?\s*\]|$)", "cap_drop: [ALL]"),
            (r"no-new-privileges:\s*true", "security_opt: [no-new-privileges:true]"),
            (r"^\s*(mem_limit|memory):\s*\S", "메모리 상한(mem_limit 또는 deploy.resources.limits.memory)"),
            (r"^\s*pids_limit:\s*\d", "pids_limit"),
            (r"^\s*user:\s*\S", "user"),
        ]
        for pattern, label in need:
            if not re.search(pattern, joined, re.MULTILINE):
                problems.append(f"{where}: 서비스 {name}에 {label}이 없습니다")
        if re.search(r"^\s*cap_drop:\s*$", joined, re.MULTILINE) and not re.search(r"^\s*-\s*\"?ALL\"?\s*$", joined, re.MULTILINE):
            problems.append(f"{where}: 서비스 {name}의 cap_drop에 ALL이 없습니다")
        for no, line in body:
            s = line.strip()
            checks = [
                (r"^privileged:\s*true\b", "privileged는 쓰지 않습니다"),
                (r"^(network_mode|pid|ipc):\s*\"?host\"?\b", "호스트 네트워크·pid·ipc를 공유하지 않습니다"),
                (r"^devices:", "장치를 넘기지 않습니다"),
                (r"docker\.sock", "docker.sock을 컨테이너에 넣지 않습니다"),
                (r"seccomp[:=]\s*unconfined", "seccomp를 끄지 않습니다"),
                (r"^cap_add:", "capability를 더하지 않습니다"),
                (r"^user:\s*\"?(0|root)(:|\"|$)", "root로 돌리지 않습니다"),
            ]
            for pattern, message in checks:
                if re.search(pattern, s):
                    problems.append(f"{rel}:{no}: 서비스 {name}: {message}")
            m = re.match(r"^image:\s*\"?([^\"\s]+)", s)
            if m and "@sha256:" not in m.group(1):
                problems.append(f"{rel}:{no}: 서비스 {name}: image {m.group(1)}는 다이제스트(@sha256:…)로 고정해야 합니다")
            m = re.match(r"^-\s*\"?([^\"\s]+)\"?\s*$", s)
            if m and re.search(r":\d+(/\w+)?$", m.group(1)) and _in_ports(body, no):
                if not PRIVATE_BIND.match(m.group(1)):
                    problems.append(f"{rel}:{no}: 서비스 {name}: 포트 {m.group(1)}는 사설·루프백 주소나 변수에만 묶어야 합니다")


def _in_ports(body: list[tuple[int, str]], no: int) -> bool:
    """줄 no가 ports: 목록 안인지(가장 가까운 위쪽 키가 ports)."""
    key = None
    for n, line in body:
        if n >= no:
            break
        s = line.strip()
        if re.match(r"^[A-Za-z_][\w.-]*:", s):
            key = s.split(":", 1)[0]
    return key == "ports"


WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"}
LONG_RUNNING = {"Deployment", "StatefulSet", "DaemonSet"}
K8S_API_CLIENT = re.compile(r"mookko\.dev/kubernetes-api-client:\s*\"?true\"?")


def documents(text: str):
    """`---`로 나눈 문서마다 (시작 줄 번호, 줄 목록)."""
    start, lines = 1, []
    for no, line in enumerate(text.splitlines(), 1):
        if line.rstrip() == "---":
            if lines:
                yield start, lines
            start, lines = no + 1, []
        else:
            lines.append(line)
    if lines:
        yield start, lines


def top_value(lines: list[str], key: str) -> str | None:
    for line in lines:
        m = re.match(rf"^{key}:\s*\"?([^\"#\s]+)", line)
        if m:
            return m.group(1)
    return None


def metadata_value(lines: list[str], key: str) -> str | None:
    """맨 앞 metadata: 바로 아래 칸(labels 등 더 깊은 칸은 보지 않음)."""
    inside = False
    child = None
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            inside = line.startswith("metadata:")
            continue
        if not inside:
            continue
        child = indent if child is None else child
        m = re.match(rf"^{key}:\s*\"?([^\"#\s]+)", line.strip())
        if indent == child and m:
            return m.group(1)
    return None


def container_items(lines: list[str], start: int):
    """containers:·initContainers: 아래 항목마다 (종류, 시작 줄 번호, 줄 목록)."""
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)(containers|initContainers):\s*$", lines[i])
        if not m:
            i += 1
            continue
        key_indent, kind = len(m.group(1)), m.group(2)
        i += 1
        item: tuple[str, int, list[str]] | None = None
        item_indent = None
        while i < len(lines):
            line = lines[i]
            if line.strip() and not line.lstrip().startswith("#"):
                indent = len(line) - len(line.lstrip())
                if indent < key_indent or (indent == key_indent and not line.lstrip().startswith("- ")):
                    break
                if line.lstrip().startswith("- ") and (item_indent is None or indent == item_indent):
                    item_indent = indent
                    if item:
                        yield item
                    item = (kind, start + i, [])
            if item:
                item[2].append(line)
            i += 1
        if item:
            yield item


def section(block: str, key: str) -> str:
    """block 안 `key:` 아래로 더 깊게 들여 쓴 줄들."""
    lines = block.splitlines()
    for i, line in enumerate(lines):
        m = re.match(rf"^(\s*)(-\s*)?{key}:\s*(\{{.*\}})?\s*$", line)
        if m and m.group(3):  # 한 줄 모양 `key: {a: 1, b: 2}`
            return "\n".join(part.strip() for part in m.group(3)[1:-1].split(","))
        if m:
            indent = len(m.group(1))
            out = []
            for nxt in lines[i + 1:]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                out.append(nxt)
            return "\n".join(out)
    return ""


def check_workload(rel: str, start: int, lines: list[str], kind: str, label: str, problems: list[str]) -> None:
    doc = "\n".join(lines)
    need = [
        (r"^\s*runAsNonRoot:\s*true\b", "runAsNonRoot: true"),
        (r"^\s*allowPrivilegeEscalation:\s*false\b", "allowPrivilegeEscalation: false"),
        (r"^\s*readOnlyRootFilesystem:\s*true\b", "readOnlyRootFilesystem: true"),
        (r"^\s*drop:\s*\[\s*\"?ALL\"?\s*\]|^\s*drop:\s*\n\s*-\s*\"?ALL\"?\s*$", "capabilities.drop: [ALL]"),
        (r"seccompProfile:\s*\n\s*type:\s*RuntimeDefault\b", "seccompProfile.type: RuntimeDefault"),
    ]
    if not K8S_API_CLIENT.search(doc):
        need.append((r"^\s*automountServiceAccountToken:\s*false\b", "automountServiceAccountToken: false"))
    for pattern, what in need:
        if not re.search(pattern, doc, re.MULTILINE):
            problems.append(f"{rel}:{start}: {label}에 {what}이 없습니다")
    forbid = [
        (r"^(privileged|hostNetwork|hostPID|hostIPC):\s*true\b", "특권·호스트 네트워크·pid·ipc를 쓰지 않습니다"),
        (r"^(-\s*)?hostPath:", "hostPath를 붙이지 않습니다"),
        (r"^add:", "capability를 더하지 않습니다"),
        (r"^runAsUser:\s*0\b", "root(UID 0)로 돌리지 않습니다"),
        (r"^type:\s*Unconfined\b", "seccomp·AppArmor를 끄지 않습니다"),
        (r"^secretKeyRef:", "비밀값을 환경 변수로 넘기지 않습니다(읽기 전용 파일로)"),
    ]
    for offset, line in enumerate(lines):
        s = line.strip()
        for pattern, message in forbid:
            if re.search(pattern, s):
                problems.append(f"{rel}:{start + offset}: {label}: {message}")
    for ckind, cstart, body in container_items(lines, start):
        block = "\n".join(body)
        cname = re.search(r"name:\s*\"?([^\"#\s]+)", block)
        clabel = f"{label}의 {ckind[:-1]} {cname.group(1) if cname else '?'}"
        image = re.search(r"^\s*(-\s*)?image:\s*\"?([^\"#\s]+)", block, re.MULTILINE)
        if not image or "@sha256:" not in image.group(2):
            problems.append(f"{rel}:{cstart}: {clabel}: image는 다이제스트(@sha256:…)로 고정해야 합니다")
        resources = section(block, "resources")
        for part in ("requests", "limits"):
            body_text = section(resources, part)
            for res in ("cpu", "memory"):
                if not re.search(rf"^\s*{res}:\s*\S", body_text, re.MULTILINE):
                    problems.append(f"{rel}:{cstart}: {clabel}: resources.{part}.{res}이 없습니다")
        if ckind == "containers" and kind in LONG_RUNNING:
            for probe in ("readinessProbe", "livenessProbe"):
                if not re.search(rf"^\s*{probe}:", block, re.MULTILINE):
                    problems.append(f"{rel}:{cstart}: {clabel}: {probe}가 없습니다")


def check_kubernetes(rel: str, text: str, problems: list[str], namespaces: dict[str, str], deny: set[str]) -> None:
    for start, lines in documents(text):
        kind = top_value(lines, "kind")
        if not kind:
            continue
        doc = "\n".join(lines)
        where = f"{rel}:{start}"
        name = metadata_value(lines, "name") or "?"
        label = f"{kind} {name}"
        if kind in WORKLOADS:
            check_workload(rel, start, lines, kind, label, problems)
        elif kind == "Service":
            m = re.search(r"^\s+type:\s*\"?(NodePort|LoadBalancer)\b", doc, re.MULTILINE)
            if m:
                problems.append(f"{where}: {label}: type {m.group(1)}는 쓰지 않습니다(ClusterIP, 바깥은 라우터·Gateway만)")
        elif kind == "Namespace":
            if not re.search(r"pod-security\.kubernetes\.io/enforce:\s*\"?restricted\"?", doc):
                problems.append(f"{where}: {label}에 라벨 pod-security.kubernetes.io/enforce: restricted가 없습니다")
            namespaces[name] = where
        elif kind == "NetworkPolicy":
            types = section(doc, "policyTypes")
            if (re.search(r"^\s+podSelector:\s*\{\s*\}", doc, re.MULTILINE)
                    and re.search(r"\bIngress\b", types) and re.search(r"\bEgress\b", types)
                    and not re.search(r"^\s+(ingress|egress):", doc, re.MULTILINE)):
                deny.add(metadata_value(lines, "namespace") or "default")
        elif kind == "PersistentVolume":
            if not re.search(r"^\s+persistentVolumeReclaimPolicy:\s*Retain\b", doc, re.MULTILINE):
                problems.append(f"{where}: {label}: persistentVolumeReclaimPolicy: Retain이어야 합니다(없으면 지울 때 데이터가 사라짐)")
        elif kind == "StorageClass":
            if not re.search(r"^reclaimPolicy:\s*Retain\b", doc, re.MULTILINE):
                problems.append(f"{where}: {label}: reclaimPolicy: Retain이어야 합니다(없으면 기본값 Delete)")


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    problems: list[str] = []
    counts = {"dockerfile": 0, "compose": 0, "kubernetes": 0}
    namespaces: dict[str, str] = {}
    deny: set[str] = set()
    for kind, path, rel in files(root):
        counts[kind] += 1
        text = path.read_text(encoding="utf-8")
        if kind == "kubernetes":
            check_kubernetes(rel.as_posix(), text, problems, namespaces, deny)
        elif kind == "dockerfile":
            check_dockerfile(rel.as_posix(), text, problems)
        else:
            check_compose(rel.as_posix(), text, problems)
    for ns, where in sorted(namespaces.items()):
        if ns not in deny:
            problems.append(f"{where}: Namespace {ns}에 기본 차단 NetworkPolicy(podSelector: {{}}, Ingress·Egress, 허용 규칙 없음)가 없습니다")
    for p in problems:
        print(p)
    if problems:
        print(f"container check failed ({len(problems)} problems)")
        return 1
    print(
        f"container check passed ({counts['dockerfile']} Dockerfiles, {counts['compose']} compose files, "
        f"{counts['kubernetes']} Kubernetes manifests)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

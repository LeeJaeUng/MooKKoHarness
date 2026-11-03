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
  - 워크로드(Deployment·StatefulSet·DaemonSet·Job·CronJob·Pod·Argo Rollout): **컨테이너마다**(initContainer 포함)
    runAsNonRoot: true·seccompProfile RuntimeDefault(파드 기본값 물려받음), allowPrivilegeEscalation: false,
    readOnlyRootFilesystem: true, capabilities.drop [ALL]. 파드에 automountServiceAccountToken: false(Kubernetes API를 부르는
    운영툴 배포기만 맨 앞 metadata.annotations의 `mookko.dev/kubernetes-api-client: "true"`로 예외). Rollout이 workloadRef로
    Deployment를 가리키면 파드 칸은 그 Deployment에서 보고, 짝(HPA·PDB)은 Rollout이 가짐(mookko-rust-qa 11-03)
  - 보안 칸의 흐름 모양(`containers: [ … ]`·`securityContext: { … }`), kind List, template·containers가 있는 모르는 종류는
    검사하지 못하므로 실패
  - 워크로드 금지: privileged·hostNetwork·hostPID·hostIPC: true, hostPath, hostPort, capabilities.add, runAsUser 0,
    반대 값(runAsNonRoot: false·allowPrivilegeEscalation: true·readOnlyRootFilesystem: false), Unconfined,
    secretKeyRef·envFrom secretRef(비밀값은 읽기 전용 파일로). true·false는 대소문자·yes/no를 함께 봄
  - 컨테이너마다: image 다이제스트 고정, resources.requests·limits의 cpu·memory. 오래 도는 것(Deployment·StatefulSet·
    DaemonSet)의 containers는 readinessProbe·livenessProbe도
  - 멀티 AZ(live-gap A5, deploy-containers §3): Deployment·StatefulSet은 topologySpreadConstraints에 topologyKey
    topology.kubernetes.io/zone·maxSkew 1, spec.replicas를 적었으면 MIN_REPLICAS 이상. HorizontalPodAutoscaler는
    minReplicas가 MIN_REPLICAS 이상(없으면 기본 1이라 실패). AZ 3개에 하나씩, AZ 하나를 잃어도 버티는 수
  - 짝(HOST-01, mookko-rust-qa 2026-11-03): 오래 도는 워크로드(Deployment·StatefulSet)마다 같은 네임스페이스에
    HorizontalPodAutoscaler(scaleTargetRef.name = 워크로드 이름)와 PodDisruptionBudget(이름이 같거나 selector
    matchLabels 값에 워크로드 이름)이 있어야 함
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


WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod", "Rollout"}
LONG_RUNNING = {"Deployment", "StatefulSet", "DaemonSet", "Rollout"}
ZONE_SPREAD = {"Deployment", "StatefulSet", "Rollout"}
# 흐름 모양(`key: [ … ]`·`key: { … }`)은 이 검사가 안을 읽지 못하므로 보안 칸에는 쓰지 못하게 한다(mookko-rust-qa 11-03).
FLOW_FORBIDDEN = re.compile(r"^\s*(-\s*)?(containers|initContainers|securityContext|capabilities|volumes|env|envFrom):\s*[\[{]")
TRUE = r"(?i:true|yes|on)"
FALSE = r"(?i:false|no|off)"
MIN_REPLICAS = 3  # AZ 3개에 하나씩(deploy-containers §3 멀티 AZ, PM 대행 2026-11-03)
K8S_API_CLIENT = re.compile(r"mookko\.dev/kubernetes-api-client:\s*\"?true\"?")


def documents(text: str):
    """`---`로 나눈 문서마다 (시작 줄 번호, 줄 목록)."""
    start, lines = 1, []
    for no, line in enumerate(text.splitlines(), 1):
        if re.match(r"^---\s*(#.*)?$", line.rstrip()):
            if lines:
                yield start, lines
            start, lines = no + 1, []
        else:
            lines.append(line)
    if lines:
        yield start, lines


def top_value(lines: list[str], key: str) -> str | None:
    for line in lines:
        m = re.match(rf"^[\"']?{key}[\"']?:\s*[\"']?([^\"'#\s]+)", line)
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


def pod_level(lines: list[str], start: int) -> str:
    """컨테이너 항목을 뺀 나머지(파드 수준 칸)."""
    inside = {no for _, cstart, body in container_items(lines, start) for no in range(cstart, cstart + len(body))}
    return "\n".join(line for i, line in enumerate(lines) if start + i not in inside)


def check_workload(rel: str, start: int, lines: list[str], kind: str, label: str, problems: list[str]) -> None:
    doc = "\n".join(lines)
    for offset, line in enumerate(lines):
        if FLOW_FORBIDDEN.search(line):
            problems.append(f"{rel}:{start + offset}: {label}: 흐름 모양({line.strip()[:40]})은 검사하지 못합니다. 블록 모양으로 쓰세요")
    if kind == "Rollout" and re.search(r"^\s+workloadRef:", doc, re.MULTILINE) and not re.search(r"^\s+template:", doc, re.MULTILINE):
        return  # 파드 틀은 가리키는 Deployment에 있고, 그쪽에서 검사함(짝·zone은 Rollout 이름으로)
    pod = pod_level(lines, start)
    pod_sc = section(section(pod, "spec") or pod, "securityContext")
    items = list(container_items(lines, start))
    if not items:
        problems.append(f"{rel}:{start}: {label}에 containers가 없습니다(검사할 수 없음)")
    if not re.search(r"^\s*automountServiceAccountToken:\s*" + FALSE + r"\b", pod, re.MULTILINE) and not api_client(lines):
        problems.append(f"{rel}:{start}: {label}에 automountServiceAccountToken: false가 없습니다")
    for ckind, cstart, body in items:
        block = "\n".join(body)
        cname = re.search(r"name:\s*[\"']?([^\"'#\s]+)", block)
        clabel = f"{label}의 {ckind[:-1]} {cname.group(1) if cname else '?'}"
        sc = section(block, "securityContext")
        # 파드 기본값을 물려받는 칸(runAsNonRoot·seccompProfile)과 컨테이너에만 있는 칸
        if not re.search(r"^\s*runAsNonRoot:\s*" + TRUE + r"\b", sc or pod_sc, re.MULTILINE) and not (
                not sc_has(sc, "runAsNonRoot") and re.search(r"^\s*runAsNonRoot:\s*" + TRUE + r"\b", pod_sc, re.MULTILINE)):
            problems.append(f"{rel}:{cstart}: {clabel}에 runAsNonRoot: true가 없습니다(파드 기본값 포함)")
        seccomp = section(sc, "seccompProfile") if sc_has(sc, "seccompProfile") else section(pod_sc, "seccompProfile")
        if not re.search(r"^\s*type:\s*RuntimeDefault\b", seccomp, re.MULTILINE):
            problems.append(f"{rel}:{cstart}: {clabel}에 seccompProfile.type: RuntimeDefault가 없습니다(파드 기본값 포함)")
        if not re.search(r"^\s*allowPrivilegeEscalation:\s*" + FALSE + r"\b", sc, re.MULTILINE):
            problems.append(f"{rel}:{cstart}: {clabel}에 allowPrivilegeEscalation: false가 없습니다")
        if not re.search(r"^\s*readOnlyRootFilesystem:\s*" + TRUE + r"\b", sc, re.MULTILINE):
            problems.append(f"{rel}:{cstart}: {clabel}에 readOnlyRootFilesystem: true가 없습니다")
        drop = section(section(sc, "capabilities"), "drop")
        if not (re.search(r"^\s*drop:\s*\[\s*[\"']?ALL[\"']?\s*\]", section(sc, "capabilities") , re.MULTILINE)
                or re.search(r"^\s*-\s*[\"']?ALL[\"']?\s*$", drop, re.MULTILINE)):
            problems.append(f"{rel}:{cstart}: {clabel}에 capabilities.drop: [ALL]이 없습니다")
        image = re.search(r"^\s*(-\s*)?image:\s*[\"']?([^\"'#\s]+)", block, re.MULTILINE)
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
    forbid = [
        (r"^(privileged|hostNetwork|hostPID|hostIPC):\s*" + TRUE + r"\b", "특권·호스트 네트워크·pid·ipc를 쓰지 않습니다"),
        (r"^(-\s*)?hostPath:", "hostPath를 붙이지 않습니다"),
        (r"^(-\s*)?hostPort:", "hostPort를 쓰지 않습니다"),
        (r"^add:", "capability를 더하지 않습니다"),
        (r"^runAsUser:\s*0\b", "root(UID 0)로 돌리지 않습니다"),
        (r"^runAsNonRoot:\s*" + FALSE + r"\b", "runAsNonRoot를 끄지 않습니다"),
        (r"^allowPrivilegeEscalation:\s*" + TRUE + r"\b", "권한 상승을 허용하지 않습니다"),
        (r"^readOnlyRootFilesystem:\s*" + FALSE + r"\b", "루트 파일 시스템을 쓰기로 열지 않습니다"),
        (r"^type:\s*Unconfined\b", "seccomp·AppArmor를 끄지 않습니다"),
        (r"^(-\s*)?secretKeyRef:|^(-\s*)?secretRef:", "비밀값을 환경 변수로 넘기지 않습니다(읽기 전용 파일로)"),
    ]
    for offset, line in enumerate(lines):
        s = line.strip()
        for pattern, message in forbid:
            if re.search(pattern, s):
                problems.append(f"{rel}:{start + offset}: {label}: {message}")
    if kind in ZONE_SPREAD:
        spread = section(doc, "topologySpreadConstraints")
        if not (re.search(r"topologyKey:\s*[\"']?topology\.kubernetes\.io/zone\b", spread)
                and re.search(r"maxSkew:\s*1\b", spread)):
            problems.append(f"{rel}:{start}: {label}에 zone 분산(topologySpreadConstraints topologyKey "
                            f"topology.kubernetes.io/zone, maxSkew: 1)이 없습니다(멀티 AZ)")
        replicas = child_value(section(doc, "spec"), "replicas")
        if replicas is not None and (not replicas.isdigit() or int(replicas) < MIN_REPLICAS):
            problems.append(f"{rel}:{start}: {label}: replicas {replicas}는 {MIN_REPLICAS} 이상이어야 합니다(AZ 하나를 잃어도 버티는 수)")


def sc_has(sc: str, key: str) -> bool:
    return bool(re.search(rf"^\s*{key}:", sc, re.MULTILINE))


def child_value(block: str, key: str) -> str | None:
    """block의 첫 들여쓰기 단계에 있는 key 값(더 깊은 칸은 보지 않음)."""
    indent = None
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        level = len(line) - len(line.lstrip())
        indent = level if indent is None else indent
        m = re.match(rf"^{key}:\s*[\"']?([^\"'#\s]+)", line.strip())
        if level == indent and m:
            return m.group(1)
    return None


def api_client(lines: list[str]) -> bool:
    """Kubernetes API를 부르는 운영툴 배포기 표시: 맨 앞 metadata.annotations 안에 있을 때만 인정."""
    meta = section("\n".join(l for l in lines), "metadata")
    return bool(K8S_API_CLIENT.search(section(meta, "annotations")))


def check_kubernetes(rel: str, text: str, problems: list[str], namespaces: dict[str, str], deny: set[str],
                     pairs: dict[str, dict]) -> None:
    for start, lines in documents(text):
        kind = top_value(lines, "kind")
        if not kind:
            continue
        doc = "\n".join(lines)
        where = f"{rel}:{start}"
        name = metadata_value(lines, "name") or "?"
        ns = metadata_value(lines, "namespace") or "default"
        label = f"{kind} {name}"
        if kind in WORKLOADS:
            check_workload(rel, start, lines, kind, label, problems)
            ref = re.search(r"^\s+name:\s*[\"']?([\w.-]+)", section(doc, "workloadRef"), re.MULTILINE)
            if kind == "Rollout" and ref:
                pairs["refs"].add((ns, ref.group(1)))
            if kind in ZONE_SPREAD:
                pairs["workloads"][(ns, name)] = (where, label)
        elif kind == "List":
            problems.append(f"{where}: kind List는 검사하지 못합니다. 문서를 `---`로 나눠 쓰세요")
        elif re.search(r"^\s+template:", doc, re.MULTILINE) and re.search(r"^\s+(-\s*)?containers:", doc, re.MULTILINE):
            problems.append(f"{where}: {label}: 모르는 워크로드 종류라 검사하지 못합니다(검사에 종류를 더하세요)")
        elif kind == "PodDisruptionBudget":
            pairs["pdb"].add((ns, name))
            for value in re.findall(r"[\w./-]+:\s*\"?([\w.-]+)", section(doc, "matchLabels")):
                pairs["pdb"].add((ns, value))
        elif kind == "HorizontalPodAutoscaler":
            target = re.search(r"^\s*name:\s*\"?([\w.-]+)", section(doc, "scaleTargetRef"), re.MULTILINE)
            if target:
                pairs["hpa"].add((ns, target.group(1)))
            m = re.search(r"^\s+minReplicas:\s*(\d+)", doc, re.MULTILINE)
            if not m or int(m.group(1)) < MIN_REPLICAS:
                found = m.group(1) if m else "없음(기본 1)"
                problems.append(f"{where}: {label}: minReplicas {found}는 {MIN_REPLICAS} 이상이어야 합니다(AZ 하나를 잃어도 버티는 수)")
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
    pairs: dict[str, dict] = {"workloads": {}, "hpa": set(), "pdb": set(), "refs": set()}
    for kind, path, rel in files(root):
        counts[kind] += 1
        text = path.read_text(encoding="utf-8")
        if kind == "kubernetes":
            check_kubernetes(rel.as_posix(), text, problems, namespaces, deny, pairs)
        elif kind == "dockerfile":
            check_dockerfile(rel.as_posix(), text, problems)
        else:
            check_compose(rel.as_posix(), text, problems)
    for key, (where, label) in sorted(pairs["workloads"].items()):
        if key in pairs["refs"]:
            continue  # Argo Rollout이 workloadRef로 가리키는 Deployment: 짝은 Rollout이 가짐
        if key not in pairs["hpa"]:
            problems.append(f"{where}: {label}에 짝 HorizontalPodAutoscaler(scaleTargetRef.name: {key[1]})가 없습니다")
        if key not in pairs["pdb"]:
            problems.append(f"{where}: {label}에 짝 PodDisruptionBudget이 없습니다")
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

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
    readOnlyRootFilesystem: true, capabilities.drop [ALL]. 파드에 automountServiceAccountToken: false(예외 없음). Kubernetes API를
    부르는 워크로드는 맨 앞 metadata.annotations의 `mookko.dev/kubernetes-api-client: "true"` 표시와 제품
    docs/policy/api-clients.json 등록(네임스페이스·워크로드 이름)이 둘 다 있어야 하고, 토큰은 등록한 serviceAccountName의
    projected serviceAccountToken(expirationSeconds ≤ 3600)으로만 붙인다(보안 담당 2026-11-04, security.md §5.1). Rollout이 workloadRef로
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
- 보안 등록부(제품 docs/policy/, 보안 담당 정본, conventions/security.md SC-*, 관문 SEC-02·SEC-04). 닫힌 쪽(SC-REG-1·2):
  node-pools.json·privileged-allowlist.json은 늘 있어야 하고(빈 목록이면 아무것도 허용하지 않음), image-registries.json은
  Dockerfile·Compose·Kubernetes 매니페스트가 하나라도 있으면 있어야 한다. 없으면 실패(등록부를 지워 검사를 끄지 못하게).
  보안 규칙(풀·샌드박스)은 YAML을 실제로 풀어(PyYAML safe_load, Linux python3-yaml) 읽는다 — 흐름 모양·따옴표도 같게 봄(SC-SBX-1).
  PyYAML이 없으면 실패한다.
  - node-pools.json(SC-NODE-2): 풀마다 {name, key, value, namespaces}. 워크로드의 tolerations·nodeSelector·nodeAffinity가
    전용 풀(key·value)을 가리키면 네임스페이스가 그 풀의 namespaces에 있어야 하고, 그 namespaces의 워크로드는
    nodeAffinity requiredDuringSchedulingIgnoredDuringExecution으로 자기 풀을 골라야 함(taint만으로는 막히지 않음).
    daemonSetNamespaces(목록)의 네임스페이스는 DaemonSet에 한해 모든 전용 풀을 받을 수 있음(노드 검사·런타임 감지처럼 모든
    노드에 떠야 하는 것, host-security §7.2). 다른 종류(Deployment·Job 등)는 그 네임스페이스여도 예외 없음
  - 라벨 mookko.io/input: untrusted(metadata·파드 틀 labels, SC-SBX-1·3): runtimeClassName: gvisor, 이름이 sandbox인 풀이 있으면 그 namespaces 안,
    secret 볼륨·serviceAccountToken 투영·serviceAccountName(default 빼고)·Kubernetes API 예외 주석 없음
  - privileged-allowlist.json(SC-PRIV-1): 항목마다 {image(다이제스트), reason, owner, reviewed}. 네임스페이스 mookko-security의
    워크로드는 모든 이미지가 여기 있을 때만 특권·호스트 공유·hostPath와 컨테이너 권한 칸 예외를 받음(이미지·자원·probe·
    비밀값 환경 변수 규칙은 그대로). Namespace는 mookko-security만 enforce: privileged를 받음
  - image-registries.json(SC-VULN-4): {registries: [접두어…]}. 접두어는 `/`로 끝나야 함(경로 마디 경계 — `…/mookko`가
    `…/mookko-evil/`을 통과시키지 않게). Dockerfile FROM(빌드 단계 별칭 빼고)·Compose image·컨테이너 image가 이 접두어 중
    하나로 시작해야 함(바깥 레지스트리에서 바로 끌지 않음)
YAML 해석기 없이 들여쓰기로만 읽는다(표준 라이브러리만, tools.md). 실패하면 `파일:줄: 이유`를 한 줄씩 내고 1로 끝난다.

사용: python3 -X utf8 ci/check-containers.py [저장소 루트]
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml  # 보안 규칙만 YAML을 풀어 읽음(SC-SBX-1). 하네스 CI(Linux)는 python3-yaml이 있음
except ImportError:  # 없으면 load_security가 실패로 알림(조용히 꺼지지 않게)
    yaml = None

SKIP_DIRS = {".git", "target", "node_modules", ".claude", "data", "dist"}
SECRET_NAME = re.compile(r"(PASSWORD|SECRET|TOKEN|PRIVATE_KEY|API_KEY)", re.IGNORECASE)
UNTRUSTED_LABEL = ("mookko.io/input", "untrusted")  # SC-SBX-1 바깥 입력 작업자 표시
PRIV_NAMESPACE = "mookko-security"  # 특권 예외를 받는 단 하나의 네임스페이스(conventions/security.md SC-PRIV-1)
PRIVATE_BIND = re.compile(r"^(\$\{[^}]+\}|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+|127\.\d+\.\d+\.\d+|\[::1\]):")


def files(root: Path):
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or any(p in SKIP_DIRS for p in rel.parts):
            continue
        name = path.name
        if name.endswith(".txt"):
            continue  # 하네스 표본(ci/fixtures, 이름 끝 .txt)은 실제 설정이 아님
        if name == "Dockerfile" or name.startswith("Dockerfile.") or name.endswith(".Dockerfile"):
            yield "dockerfile", path, rel
        elif re.fullmatch(r"(docker-)?compose[\w.-]*\.ya?ml", name):
            yield "compose", path, rel
        elif name.endswith((".yaml", ".yml")):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^apiVersion:", text, re.MULTILINE) and re.search(r"^kind:", text, re.MULTILINE):
                yield "kubernetes", path, rel


def check_dockerfile(rel: str, text: str, problems: list[str], sec: dict | None = None) -> None:
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
            if image not in stages:
                check_registry(rel, no, f"FROM {image}", image, sec, problems)
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


def check_compose(rel: str, text: str, problems: list[str], sec: dict | None = None) -> None:
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
            if m:
                check_registry(rel, no, f"서비스 {name}: image {m.group(1)}", m.group(1), sec, problems)
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


def check_workload(rel: str, start: int, lines: list[str], kind: str, label: str, problems: list[str],
                   ns: str = "default", sec: dict | None = None) -> None:
    doc = "\n".join(lines)
    sec = sec or {}
    for offset, line in enumerate(lines):
        if FLOW_FORBIDDEN.search(line):
            problems.append(f"{rel}:{start + offset}: {label}: 흐름 모양({line.strip()[:40]})은 검사하지 못합니다. 블록 모양으로 쓰세요")
    if kind == "Rollout" and re.search(r"^\s+workloadRef:", doc, re.MULTILINE) and not re.search(r"^\s+template:", doc, re.MULTILINE):
        replicas = child_value(section(doc, "spec"), "replicas")
        if replicas is not None and (not replicas.isdigit() or int(replicas) < MIN_REPLICAS):
            problems.append(f"{rel}:{start}: {label}: replicas {replicas}는 {MIN_REPLICAS} 이상이어야 합니다(AZ 하나를 잃어도 버티는 수)")
        return  # 파드 틀은 가리키는 Deployment에 있고, 그쪽에서 검사함(짝·zone은 Rollout 이름으로)
    pod = pod_level(lines, start)
    pod_sc = section(section(pod, "spec") or pod, "securityContext")
    items = list(container_items(lines, start))
    if not items:
        problems.append(f"{rel}:{start}: {label}에 containers가 없습니다(검사할 수 없음)")
    images = [m.group(2) for _, _, body in items
              for m in [re.search(r"^\s*(-\s*)?image:\s*[\"']?([^\"'#\s]+)", "\n".join(body), re.MULTILINE)] if m]
    # 특권 예외(SC-PRIV-1): mookko-security 네임스페이스이고 모든 컨테이너 이미지가 privileged-allowlist.json에 있을 때만
    privileged_ok = (ns == PRIV_NAMESPACE and sec.get("privileged") is not None and bool(images)
                     and len(images) == len(items) and all(img in sec["privileged"] for img in images))
    check_security(rel, start, lines, doc, label, ns, sec, problems)
    check_service_account(rel, start, lines, doc, label, ns, sec, problems)
    for ckind, cstart, body in items:
        block = "\n".join(body)
        cname = re.search(r"name:\s*[\"']?([^\"'#\s]+)", block)
        clabel = f"{label}의 {ckind[:-1]} {cname.group(1) if cname else '?'}"
        sc = section(block, "securityContext")
        image = re.search(r"^\s*(-\s*)?image:\s*[\"']?([^\"'#\s]+)", block, re.MULTILINE)
        if not image or "@sha256:" not in image.group(2):
            problems.append(f"{rel}:{cstart}: {clabel}: image는 다이제스트(@sha256:…)로 고정해야 합니다")
        if image:
            check_registry(rel, cstart, f"{clabel}: image {image.group(2)}", image.group(2), sec, problems)
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
        if privileged_ok:
            continue  # 등록한 특권 이미지(Falco·Tetragon 등)는 컨테이너 권한 칸을 보지 않음
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
    if privileged_ok:
        forbid = forbid[-1:]  # 비밀값 환경 변수 금지만 남김
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


def pod_template(obj: dict) -> tuple[dict, list[dict]]:
    """풀어 읽은 워크로드에서 (파드 spec, labels 묶음들). Pod·Deployment류·Job·CronJob."""
    labels = [(obj.get("metadata") or {}).get("labels") or {}]
    spec = obj.get("spec") or {}
    if obj.get("kind") == "Pod":
        return spec, labels
    if obj.get("kind") == "CronJob":
        spec = ((spec.get("jobTemplate") or {}).get("spec")) or {}
    template = spec.get("template") or {}
    labels.append((template.get("metadata") or {}).get("labels") or {})
    return template.get("spec") or {}, labels


def pool_used(pod: dict, pool: dict) -> bool:
    """파드가 tolerations·nodeSelector·nodeAffinity로 그 풀을 고르는지."""
    key, value = pool["key"], pool["value"]
    for tol in pod.get("tolerations") or []:
        if not isinstance(tol, dict):
            continue
        if tol.get("key") == key and (tol.get("operator") == "Exists" or str(tol.get("value")) == value):
            return True
    if str((pod.get("nodeSelector") or {}).get(key)) == value:
        return True
    affinity = ((pod.get("affinity") or {}).get("nodeAffinity")) or {}
    terms = list(((affinity.get("requiredDuringSchedulingIgnoredDuringExecution") or {}).get("nodeSelectorTerms")) or [])
    terms += [p.get("preference") or {} for p in affinity.get("preferredDuringSchedulingIgnoredDuringExecution") or [] if isinstance(p, dict)]
    return any(isinstance(e, dict) and e.get("key") == key and value in [str(v) for v in e.get("values") or []]
               for term in terms if isinstance(term, dict) for e in term.get("matchExpressions") or [])


def pool_required(pod: dict, pool: dict) -> bool:
    """required nodeAffinity의 모든 term이 key In [value]만 고르는지(taint만으로는 막히지 않음)."""
    affinity = ((pod.get("affinity") or {}).get("nodeAffinity")) or {}
    terms = ((affinity.get("requiredDuringSchedulingIgnoredDuringExecution") or {}).get("nodeSelectorTerms")) or []
    return bool(terms) and all(
        isinstance(term, dict) and any(
            isinstance(e, dict) and e.get("key") == pool["key"] and e.get("operator") == "In"
            and [str(v) for v in e.get("values") or []] == [pool["value"]]
            for e in term.get("matchExpressions") or [])
        for term in terms)


def check_anti_affinity(where: str, label: str, pod: dict, rule: dict, problems: list[str]) -> None:
    """node-pools.json antiAffinity: notWith 네임스페이스마다 required podAntiAffinity 항목(같은 topologyKey,
    namespaces 또는 namespaceSelector가 그 네임스페이스를 가리킴)이 있어야 함(security.md §4.1 S-8)."""
    terms = ((((pod.get("affinity") or {}).get("podAntiAffinity") or {})
              .get("requiredDuringSchedulingIgnoredDuringExecution")) or [])

    def covers(term: dict, other: str) -> bool:
        if not isinstance(term, dict) or term.get("topologyKey") != rule["topologyKey"] or not isinstance(term.get("labelSelector"), dict):
            return False  # labelSelector가 없으면(null) 어떤 Pod도 고르지 않아 분리가 없음(mookko-rust-qa 11-04)
        if other in (term.get("namespaces") or []):
            return True
        sel = term.get("namespaceSelector") or {}
        if (sel.get("matchLabels") or {}).get("kubernetes.io/metadata.name") == other:
            return True
        return any(isinstance(e, dict) and e.get("key") == "kubernetes.io/metadata.name" and e.get("operator") == "In"
                   and other in (e.get("values") or []) for e in sel.get("matchExpressions") or [])

    missing = [other for other in rule["notWith"] if not any(covers(t, other) for t in terms)]
    if missing:
        problems.append(f"{where}: {label}: required podAntiAffinity({rule['topologyKey']})로 {missing} Pod와 같은 노드를 피해야 합니다"
                        f"(node-pools.json antiAffinity, SC-NODE-2)")


def check_security(rel: str, start: int, lines: list[str], doc: str, label: str, ns: str, sec: dict,
                   problems: list[str]) -> None:
    """보안 등록부 규칙(SEC-02): 노드 풀 대응표, 바깥 입력 샌드박스. YAML을 풀어 읽는다(SC-SBX-1)."""
    pools = sec.get("pools")
    where = f"{rel}:{start}"
    if yaml is None:
        return  # load_security가 이미 실패로 알림
    try:
        obj = yaml.safe_load(doc)
    except yaml.YAMLError as e:
        problems.append(f"{where}: {label}: YAML을 풀지 못했습니다({str(e).splitlines()[0]})")
        return
    if not isinstance(obj, dict):
        return
    pod, label_maps = pod_template(obj)
    if not isinstance(pod, dict):
        return
    if any(isinstance(t, dict) and not t.get("key") and t.get("operator") == "Exists" for t in pod.get("tolerations") or []):
        problems.append(f"{where}: {label}: 키 없는 `operator: Exists` toleration은 모든 taint를 받으므로 쓰지 않습니다"
                        f"(받을 풀 키를 하나씩, SC-NODE-2·QA N2)")
    for rule in sec.get("anti", []):
        if ns == rule["namespace"]:
            check_anti_affinity(where, label, pod, rule, problems)
    images = [c.get("image") for key in ("containers", "initContainers") for c in pod.get(key) or [] if isinstance(c, dict)]
    # 모든 노드에 뜨는 DaemonSet: daemonSetNamespaces + 모든 이미지가 privileged-allowlist.json에 있을 때만(mookko-rust-qa 11-04)
    every_node = (obj.get("kind") == "DaemonSet" and ns in sec.get("daemon_ns", set()) and bool(images)
                  and all(img in (sec.get("privileged") or set()) for img in images))
    for pool in pools or []:
        if pool_used(pod, pool) and ns not in pool["namespaces"] and not every_node:
            problems.append(f"{where}: {label}: 네임스페이스 {ns}는 {pool['name']} 풀을 쓸 수 없습니다"
                            f"(docs/policy/node-pools.json, SC-NODE-2)")
        if ns in pool["namespaces"] and not pool_required(pod, pool):
            problems.append(f"{where}: {label}: {pool['name']} 풀 네임스페이스의 워크로드는 nodeAffinity "
                            f"requiredDuringSchedulingIgnoredDuringExecution으로 {pool['key']} In [{pool['value']}]만 골라야 합니다(SC-NODE-2)")
    key, want = UNTRUSTED_LABEL
    if not any(isinstance(m, dict) and str(m.get(key)) == want for m in label_maps):
        return
    if pod.get("runtimeClassName") != "gvisor":
        problems.append(f"{where}: {label}: mookko.io/input: untrusted이면 runtimeClassName: gvisor여야 합니다(SC-SBX-1)")
    sandbox = next((p for p in pools or [] if p["name"] == "sandbox"), None)
    if sandbox and ns not in sandbox["namespaces"]:
        problems.append(f"{where}: {label}: mookko.io/input: untrusted 워크로드는 sandbox 풀 네임스페이스에 둡니다(지금 {ns}, SC-SBX-1)")
    for volume in pod.get("volumes") or []:
        if not isinstance(volume, dict):
            continue
        if "secret" in volume:
            problems.append(f"{where}: {label}: 샌드박스 작업자에 비밀값 볼륨({volume.get('name')})을 붙이지 않습니다(SC-SBX-3)")
        sources = ((volume.get("projected") or {}).get("sources")) or []
        if any(isinstance(s, dict) and ("serviceAccountToken" in s or "secret" in s) for s in sources):
            problems.append(f"{where}: {label}: 샌드박스 작업자에 서비스 계정 토큰·비밀값을 투영하지 않습니다(SC-SBX-3)")
    if pod.get("serviceAccountName") not in (None, "default"):
        problems.append(f"{where}: {label}: 샌드박스 작업자에 서비스 계정(Workload Identity 권한)을 붙이지 않습니다(SC-SBX-3)")
    if api_client(lines):
        problems.append(f"{where}: {label}: 샌드박스 작업자는 Kubernetes API 예외 주석을 쓰지 않습니다(SC-SBX-3)")


def check_registry(rel: str, no: int, what: str, image: str, sec: dict | None, problems: list[str]) -> None:
    registries = (sec or {}).get("registries")
    if registries is not None and not image.startswith(tuple(registries)):
        problems.append(f"{rel}:{no}: {what}: 우리 레지스트리(docs/policy/image-registries.json)로 가져온 이미지만 씁니다(SC-VULN-4)")


def load_security(root: Path, problems: list[str]) -> dict:
    """제품 docs/policy/의 보안 등록부. 없는 파일은 None(그 규칙을 보지 않음)."""
    def read(name: str):
        path = root / "docs" / "policy" / name
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            problems.append(f"docs/policy/{name}:1: JSON을 읽지 못했습니다: {e}")
            return {}

    sec: dict = {"pools": None, "privileged": None, "registries": None, "api_clients": None, "wi": None}
    if yaml is None:
        problems.append("docs/policy/node-pools.json:1: PyYAML(python3-yaml)이 없어 보안 규칙을 볼 수 없습니다(하네스 CI 환경 확인)")
    pools = read("node-pools.json")
    if pools is not None:
        sec["pools"] = []
        for i, pool in enumerate(pools.get("pools", [])):
            if not (isinstance(pool, dict) and all(pool.get(k) for k in ("name", "key", "value", "namespaces"))
                    and isinstance(pool["namespaces"], list)):
                problems.append(f"docs/policy/node-pools.json:1: pools[{i}]에 name·key·value·namespaces(목록)가 있어야 합니다")
                continue
            sec["pools"].append(pool)
        anti = pools.get("antiAffinity", [])
        for i, rule in enumerate(anti if isinstance(anti, list) else [None]):
            if not (isinstance(rule, dict) and all(rule.get(k) for k in ("namespace", "notWith", "topologyKey", "reason"))
                    and isinstance(rule["notWith"], list)):
                problems.append(f"docs/policy/node-pools.json:1: antiAffinity[{i}]에 namespace·notWith(목록)·topologyKey·reason이 있어야 합니다")
            else:
                sec.setdefault("anti", []).append(rule)
        daemon_ns = pools.get("daemonSetNamespaces", [])
        if not (isinstance(daemon_ns, list) and all(isinstance(n, str) and n for n in daemon_ns)):
            problems.append("docs/policy/node-pools.json:1: daemonSetNamespaces는 네임스페이스 이름 목록이어야 합니다")
        else:
            sec["daemon_ns"] = set(daemon_ns)
    allow = read("privileged-allowlist.json")
    if allow is not None:
        sec["privileged"] = set()
        for i, item in enumerate(allow.get("images", [])):
            if not (isinstance(item, dict) and all(item.get(k) for k in ("image", "reason", "owner", "reviewed"))):
                problems.append(f"docs/policy/privileged-allowlist.json:1: images[{i}]에 image·reason·owner·reviewed가 있어야 합니다")
            elif "@sha256:" not in item["image"]:
                problems.append(f"docs/policy/privileged-allowlist.json:1: images[{i}] {item['image']}는 다이제스트로 고정해야 합니다")
            else:
                sec["privileged"].add(item["image"])
    clients = read("api-clients.json")
    if clients is not None:
        sec["api_clients"] = {}
        for i, item in enumerate(clients.get("clients", [])):
            if not (isinstance(item, dict) and all(item.get(k) for k in API_CLIENT_FIELDS)):
                problems.append(f"docs/policy/api-clients.json:1: clients[{i}]에 {'·'.join(API_CLIENT_FIELDS)}가 있어야 합니다")
                continue
            cls = item.get("class", "workload")
            if cls not in CLIENT_CLASSES:
                problems.append(f"docs/policy/api-clients.json:1: clients[{i}]: class는 {'|'.join(CLIENT_CLASSES)}입니다(지금 {cls!r})")
                continue
            platform = cls == "platform-controller"
            if item["scope"] not in ("namespace", "cluster") or not isinstance(item["rules"], list) or not all(
                    rule_shape_ok(r, subresources=platform) for r in item["rules"]):
                problems.append(f"docs/policy/api-clients.json:1: clients[{i}]: scope는 namespace|cluster, rules는 apiGroups·resources·verbs 목록"
                                f"(와일드카드 금지, 하위 자원은 platform-controller만)")
                continue
            if not platform and "allowedEscalations" in item:
                problems.append(f"docs/policy/api-clients.json:1: clients[{i}]: allowedEscalations는 class platform-controller만 씁니다(SC-NODE-6)")
                continue
            if platform:
                escs = item.get("allowedEscalations", [])
                if not (isinstance(escs, list) and all(rule_shape_ok(e, subresources=True) and isinstance(e.get("reason"), str) and e["reason"]
                                                       for e in escs)):
                    problems.append(f"docs/policy/api-clients.json:1: clients[{i}]: allowedEscalations는 [{{apiGroups, resources, verbs, reason}}] 목록입니다")
                    continue
                control = next((set(p["namespaces"]) for p in sec["pools"] or [] if p["name"] == CONTROL_POOL), set())
                if item["namespace"] not in control or item["namespace"].startswith("mookko-"):
                    problems.append(f"docs/policy/api-clients.json:1: clients[{i}]: platform-controller는 node-pools.json {CONTROL_POOL} 풀의 "
                                    f"플랫폼 네임스페이스(우리 mookko-* 서비스 빼고)에만 둡니다(지금 {item['namespace']}, SC-NODE-6)")
                    continue
            if "bindNamespaces" in item and not (isinstance(item["bindNamespaces"], list)
                                                 and all(isinstance(n, str) and n for n in item["bindNamespaces"])):
                problems.append(f"docs/policy/api-clients.json:1: clients[{i}]: bindNamespaces는 네임스페이스 이름 목록이어야 합니다")
                continue
            wide = sorted({f"{g or 'core'}/{r} {v}" for rule in item["rules"] for g in rule["apiGroups"] for r in rule["resources"]
                           for v in rule["verbs"] if escalating(g, r, v) and not escalation_allowed(item, g, r, v)})
            if wide:
                problems.append(f"docs/policy/api-clients.json:1: clients[{i}]: 권한을 넓히는 권한은 등록하지 않습니다 {wide}(SC-NODE-6)")
                continue
            if item["serviceAccount"] == "default":
                problems.append(f"docs/policy/api-clients.json:1: clients[{i}]: default 서비스 계정은 등록하지 않습니다(네임스페이스 전체가 권한을 받음)")
                continue
            sec["api_clients"][(item["namespace"], item["workload"])] = item
    registries = read("image-registries.json")
    if registries is not None:
        sec["registries"] = []
        for value in registries.get("registries", []):
            if not (isinstance(value, str) and value.endswith("/") and len(value) > 1):
                problems.append(f"docs/policy/image-registries.json:1: 접두어 {value!r}는 `/`로 끝나는 레지스트리 경로여야 합니다(마디 경계)")
            else:
                sec["registries"].append(value)
        if not sec["registries"]:
            problems.append("docs/policy/image-registries.json:1: registries(이미지 접두어 목록)가 비었습니다")
    identities = read("workload-identities.json")
    if identities is not None:
        sec["wi"] = {"by_sa": {}, "workloads": {}}
        for i, item in enumerate(identities.get("identities", [])):
            if not (isinstance(item, dict) and all(item.get(k) for k in WI_FIELDS)):
                problems.append(f"docs/policy/workload-identities.json:1: identities[{i}]에 {'·'.join(WI_FIELDS)}가 있어야 합니다")
                continue
            if item["serviceAccount"] == "default":
                problems.append(f"docs/policy/workload-identities.json:1: identities[{i}]: default 서비스 계정은 등록하지 않습니다(네임스페이스 전체가 GCP 자격을 받음)")
                continue
            key = (item["namespace"], item["serviceAccount"])
            sec["wi"]["by_sa"].setdefault(key, []).append(item)
            sec["wi"]["workloads"].setdefault(key, set()).add((item["kind"], item["namespace"], item["workload"]))
    return sec


WI_ANNOTATION = "iam.gke.io/gcp-service-account"
WI_FIELDS = ("kind", "namespace", "workload", "serviceAccount", "gcpServiceAccount", "gcpRoles", "reason", "reviewer")
REGISTERS = {"pools": "node-pools.json", "privileged": "privileged-allowlist.json", "registries": "image-registries.json",
             "api_clients": "api-clients.json", "wi": "workload-identities.json"}
ALWAYS = {"pools", "privileged", "api_clients", "wi"}  # SC-REG-1: 늘 있어야 함. image-registries는 매니페스트가 있을 때만


def missing_registers(sec: dict, manifests: int, problems: list[str]) -> list[str]:
    """빠진 등록부(SC-REG-1): 늘 있어야 하는 것과 매니페스트가 있을 때의 image-registries는 실패, 그 밖은 경고 줄."""
    warnings = []
    for key, name in REGISTERS.items():
        if sec[key] is None:
            line = f"docs/policy/{name}:1: 보안 등록부가 없습니다(보안 담당이 만듦, conventions/security.md SC-REG-1)"
            (problems if key in ALWAYS or manifests else warnings).append(line)
    return warnings


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


MAX_TOKEN_SECONDS = 3600  # projected serviceAccountToken 만료 상한(보안 담당 api-clients.json note)
API_CLIENT_FIELDS = ("namespace", "workload", "serviceAccount", "reason", "reviewed", "scope", "rules", "reviewer")
RBAC_KINDS = {"Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding"}
CLIENT_CLASSES = ("workload", "platform-controller")
CONTROL_POOL = "control"  # node-pools.json에서 플랫폼 제어기가 사는 풀 이름(보안 담당 730d41a SC-NODE-6 ①)


def rule_shape_ok(rule: object, subresources: bool) -> bool:
    """apiGroups·resources·verbs가 비지 않은 문자열 목록, 와일드카드 없음, 하위 자원은 subresources일 때만."""
    return (isinstance(rule, dict) and all(isinstance(rule.get(k), list) and rule[k] and all(isinstance(v, str) for v in rule[k])
                                           for k in ("apiGroups", "resources", "verbs"))
            and not any("*" in v for k in ("apiGroups", "resources", "verbs") for v in rule[k])
            and (subresources or not any("/" in v for v in rule["resources"])))


def escalation_allowed(entry: dict, group: str, resource: str, verb: str) -> bool:
    """platform-controller 항목의 allowedEscalations에 적힌 (그룹, 자원, 동사)인지(보안 담당 730d41a SC-NODE-6 ④)."""
    return entry.get("class") == "platform-controller" and any(
        group in e["apiGroups"] and resource in e["resources"] and verb in e["verbs"] for e in entry.get("allowedEscalations", []))


def check_rbac(sec: dict, rbac: list[tuple[str, dict]], problems: list[str]) -> None:
    """api-clients.json 등록 SA에 묶인 Role·ClusterRole이 rules(상한)를 넘지 않는지(SC-NODE-6). 와일드카드·하위 자원 금지,
    scope가 namespace면 ClusterRoleBinding으로 묶지 않음."""
    clients = sec.get("api_clients") or {}
    roles = {(o.get("kind"), (o.get("metadata") or {}).get("namespace"), (o.get("metadata") or {}).get("name")): (where, o)
             for where, o in rbac if o.get("kind") in ("Role", "ClusterRole")}
    for where, binding in rbac:
        if binding.get("kind") not in ("RoleBinding", "ClusterRoleBinding"):
            continue
        bns = (binding.get("metadata") or {}).get("namespace")
        label = f"{binding.get('kind')} {(binding.get('metadata') or {}).get('name')}"
        for subject in binding.get("subjects") or []:
            if not isinstance(subject, dict):
                continue
            kind, sname = subject.get("kind"), str(subject.get("name") or "")
            if kind == "Group" and sname.startswith("system:"):
                # system:serviceaccounts*뿐 아니라 system:authenticated·unauthenticated 등도 모든 SA(또는 누구나)를 담아
                # 등록·bindNamespaces를 비켜 감(mookko-rust-qa 추가 6 ⑤)
                problems.append(f"{where}: {label}: 시스템 Group {sname}에 권한을 주지 않습니다(SA마다 api-clients.json 등록, SC-NODE-6)")
                continue
            if kind == "User" and sname.startswith("system:serviceaccount:"):
                parts = sname.split(":")
                subject = {"kind": "ServiceAccount", "namespace": parts[2] if len(parts) > 3 else None,
                           "name": parts[3] if len(parts) > 3 else ""}
            elif kind != "ServiceAccount":
                continue
            entry = next((e for e in clients.values()
                          if e["namespace"] == subject.get("namespace", bns) and e["serviceAccount"] == subject.get("name")), None)
            if entry is None:
                problems.append(f"{where}: {label}: 서비스 계정 {subject.get('namespace', bns)}/{subject.get('name')}는 api-clients.json에 없어 "
                                f"Kubernetes 권한을 묶지 않습니다(SC-NODE-6)")
                continue
            allowed = set(entry.get("bindNamespaces") or [entry["namespace"]])
            if binding.get("kind") == "RoleBinding" and bns not in allowed:
                problems.append(f"{where}: {label}: {entry['serviceAccount']}를 묶는 RoleBinding은 bindNamespaces {sorted(allowed)}에만 둡니다"
                                f"(지금 {bns}, api-clients.json)")
            if binding.get("kind") == "ClusterRoleBinding" and entry["scope"] != "cluster":
                problems.append(f"{where}: {label}: {entry['serviceAccount']}는 scope namespace라 ClusterRoleBinding으로 묶지 않습니다(api-clients.json)")
            ref = binding.get("roleRef") or {}
            role_ns = None if ref.get("kind") == "ClusterRole" else bns
            found = roles.get((ref.get("kind"), role_ns, ref.get("name")))
            if found is None:
                problems.append(f"{where}: {label}: 묶은 {ref.get('kind')} {ref.get('name')}가 저장소에 없어 rules 상한과 대조하지 못합니다")
                continue
            role_where, role = found
            if role.get("aggregationRule"):
                problems.append(f"{role_where}: {ref.get('kind')} {ref.get('name')}: aggregationRule ClusterRole은 규칙을 대조하지 못하므로 등록 SA에 묶지 않습니다")
            for rule in role.get("rules") or []:
                if rule.get("nonResourceURLs"):
                    problems.append(f"{role_where}: {ref.get('kind')} {ref.get('name')}: nonResourceURLs는 api-clients.json rules에 없으므로 주지 않습니다")
                for group in rule.get("apiGroups") or [""]:
                    for resource in rule.get("resources") or []:
                        for verb in rule.get("verbs") or []:
                            if escalating(group, resource, verb) and not escalation_allowed(entry, group, resource, verb):
                                problems.append(f"{role_where}: {ref.get('kind')} {ref.get('name')}: {group or 'core'}/{resource} {verb}는 "
                                                f"권한을 넓히는 권한이라 주지 않습니다(SC-NODE-6)")
                                continue
                            sub_ok = entry.get("class") == "platform-controller"
                            if "*" in (group, resource, verb) or ("/" in resource and not sub_ok) or not any(
                                    group in r["apiGroups"] and resource in r["resources"] and verb in r["verbs"] for r in entry["rules"]):
                                problems.append(f"{role_where}: {ref.get('kind')} {ref.get('name')}: {group or 'core'}/{resource} {verb}는 "
                                                f"{entry['serviceAccount']}의 api-clients.json rules 상한을 넘습니다(와일드카드·하위 자원 금지)")


RBAC_OBJECTS = {"roles", "rolebindings", "clusterroles", "clusterrolebindings"}
WRITE_VERBS = {"create", "update", "patch", "delete", "deletecollection"}


# 다른 SA로 Pod를 띄울 수 있는 자원(보안 담당 fb18ab2 §5.1: pods와 Pod를 만드는 제어기의 create·update·patch)
POD_MAKERS = {("", "pods"), ("", "replicationcontrollers"), ("apps", "deployments"), ("apps", "replicasets"),
              ("apps", "statefulsets"), ("apps", "daemonsets"), ("batch", "jobs"), ("batch", "cronjobs"), ("argoproj.io", "rollouts")}


def escalating(group: str, resource: str, verb: str) -> bool:
    """권한을 넓히는 권한(보안 담당 755f466·fb18ab2 §5.1): RBAC 객체 쓰기, bind·escalate·impersonate, secrets, 서비스 계정 토큰 만들기,
    Pod·Pod를 만드는 제어기의 create·update·patch, admission 설정(webhook·정책) 쓰기, CRD 쓰기, CSR 승인·서명, persistentvolumes 만들기."""
    if verb in ("bind", "escalate", "impersonate", "approve", "sign"):
        return True
    if group == "rbac.authorization.k8s.io" and resource in RBAC_OBJECTS and verb in WRITE_VERBS:
        return True
    if group == "" and resource == "secrets":
        return True
    if (group, resource) in POD_MAKERS and verb in ("create", "update", "patch"):
        return True
    if group == "admissionregistration.k8s.io" and verb in WRITE_VERBS:
        return True
    if group == "apiextensions.k8s.io" and resource.startswith("customresourcedefinitions") and verb in WRITE_VERBS:
        return True
    if group == "certificates.k8s.io" and resource in ("certificatesigningrequests/approval", "certificatesigningrequests/status")             and verb in WRITE_VERBS:
        return True
    if group == "" and resource == "persistentvolumes" and verb == "create":
        return True
    return group == "" and resource in ("serviceaccounts/token", "serviceaccounts") and verb == "create"


def check_service_account(rel: str, start: int, lines: list[str], doc: str, label: str, ns: str, sec: dict,
                          problems: list[str]) -> None:
    """서비스 계정·API 토큰(SC-NODE-6, mookko-rust-qa 11-04 N1). 파드 틀 트리에서 판정한다.
    - automountServiceAccountToken: false(예외 없음)
    - api-client 표시나 projected serviceAccountToken이 있으면 (네임스페이스, 워크로드)가 api-clients.json에 있어야 함
    - api-clients.json에 등록한 serviceAccount는 그 등록 워크로드만 씀(다른 워크로드가 같은 SA로 RBAC를 얻지 못하게)
    - 등록 워크로드는 등록한 serviceAccountName과 projected 토큰 expirationSeconds ≤ MAX_TOKEN_SECONDS"""
    where = f"{rel}:{start}"
    if yaml is None:
        return  # load_security가 실패로 알림
    try:
        obj = yaml.safe_load(doc)
    except yaml.YAMLError:
        return  # check_security가 알림
    pod, _ = pod_template(obj if isinstance(obj, dict) else {})
    if not isinstance(pod, dict):
        return
    if pod.get("automountServiceAccountToken") is not False:
        problems.append(f"{where}: {label}에 automountServiceAccountToken: false가 없습니다(파드 틀, API 토큰은 projected 볼륨으로만)")
    name = label.split(" ", 1)[1]
    if "serviceAccount" in pod:
        problems.append(f"{where}: {label}: 옛 칸 serviceAccount 대신 serviceAccountName을 씁니다(대조를 비켜 가지 않게)")
    sa = pod.get("serviceAccountName") or pod.get("serviceAccount") or "default"  # 칸이 없으면 default SA
    identities = sec.get("wi")
    if identities is not None and (ns, sa) in identities["by_sa"] and (obj.get("kind"), ns, name) not in identities["workloads"].get((ns, sa), set()):
        problems.append(f"{where}: {label}: 서비스 계정 {sa}는 Workload Identity로 GCP 자격을 받으므로 workload-identities.json에 "
                        f"({obj.get('kind')}, {ns}, {name})가 등록돼 있어야 씁니다(토큰 마운트와 상관없음, SC-NODE-4)")
    clients = sec.get("api_clients")
    if clients is None:
        return  # 등록부 없음은 missing_registers가 실패로 알림
    seconds = [s["serviceAccountToken"].get("expirationSeconds")
               for v in pod.get("volumes") or [] if isinstance(v, dict)
               for s in ((v.get("projected") or {}).get("sources") or []) if isinstance(s, dict) and isinstance(s.get("serviceAccountToken"), dict)]
    owner = next((key for key, item in clients.items() if key[0] == ns and item["serviceAccount"] == sa), None)
    if owner is not None and owner[1] != name:
        problems.append(f"{where}: {label}: 서비스 계정 {sa}는 api-clients.json에 {owner[1]} 몫으로 등록돼 있어 다른 워크로드가 쓰지 않습니다")
    entry = clients.get((ns, name))
    if entry is not None and entry.get("kind") not in (None, obj.get("kind")):
        entry = None  # 워크로드는 (kind, ns, name)으로 가림(QA N3)
    if entry is None:
        if api_client(lines) or seconds:
            problems.append(f"{where}: {label}: API 토큰(api-client 표시·projected serviceAccountToken)은 docs/policy/api-clients.json에 "
                            f"({ns}, {name})가 있어야 합니다(보안 담당 검토 뒤 등록)")
        return
    if sa != entry["serviceAccount"]:
        problems.append(f"{where}: {label}: serviceAccountName은 등록한 {entry['serviceAccount']}여야 합니다(api-clients.json)")
    if not seconds or not all(isinstance(x, int) and 0 < x <= MAX_TOKEN_SECONDS for x in seconds):
        problems.append(f"{where}: {label}: API 토큰은 projected serviceAccountToken(expirationSeconds ≤ {MAX_TOKEN_SECONDS})으로만 붙입니다")


def api_client(lines: list[str]) -> bool:
    """Kubernetes API를 부르는 운영툴 배포기 표시: 맨 앞 metadata.annotations 안에 있을 때만 인정."""
    meta = section("\n".join(l for l in lines), "metadata")
    return bool(K8S_API_CLIENT.search(section(meta, "annotations")))


def check_kubernetes(rel: str, text: str, problems: list[str], namespaces: dict[str, str], deny: set[str],
                     pairs: dict[str, dict], sec: dict | None = None) -> None:
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
            check_workload(rel, start, lines, kind, label, problems, ns, sec)
            ref_block = section(doc, "workloadRef")
            ref = re.search(r"^\s+name:\s*[\"']?([\w.-]+)", ref_block, re.MULTILINE)
            ref_kind = re.search(r"^\s+kind:\s*[\"']?([\w.-]+)", ref_block, re.MULTILINE)
            if kind == "Rollout" and ref:
                if not ref_kind or ref_kind.group(1) != "Deployment":
                    problems.append(f"{where}: {label}: workloadRef.kind는 Deployment여야 합니다(지금 {ref_kind.group(1) if ref_kind else '없음'})")
                target = (ns, "Deployment", ref.group(1))  # 종류까지 키로(같은 이름 Rollout이 자기 자신으로 통과하지 않게, N3)
                pairs["refs"].add(target)
                pairs["ref_from"][target] = (where, label)
            if kind in ZONE_SPREAD:
                pairs["workloads"][(ns, kind, name)] = (where, label)
        elif kind == "List":
            problems.append(f"{where}: kind List는 검사하지 못합니다. 문서를 `---`로 나눠 쓰세요")
        elif re.search(r"^\s+template:", doc, re.MULTILINE) and re.search(r"^\s+(-\s*)?containers:", doc, re.MULTILINE):
            problems.append(f"{where}: {label}: 모르는 워크로드 종류라 검사하지 못합니다(검사에 종류를 더하세요)")
        elif kind == "ServiceAccount" and yaml is not None and (sec or {}).get("wi") is not None:
            try:
                obj = yaml.safe_load(doc)
            except yaml.YAMLError as e:
                problems.append(f"{where}: {label}: YAML을 풀지 못했습니다({str(e).splitlines()[0]})")
                obj = None
            gsa = (((obj or {}).get("metadata") or {}).get("annotations") or {}).get(WI_ANNOTATION) if isinstance(obj, dict) else None
            entries = sec["wi"]["by_sa"].get((ns, name), [])
            if gsa is not None and name == "default":
                problems.append(f"{where}: {label}: default 서비스 계정에는 {WI_ANNOTATION} 주석을 달지 않습니다(네임스페이스 전체가 GCP 자격을 받음, SC-NODE-4)")
            elif gsa is not None and not entries:
                problems.append(f"{where}: {label}: {WI_ANNOTATION} 주석이 있으면 workload-identities.json에 ({ns}, {name})가 있어야 합니다(SC-NODE-4)")
            elif gsa is not None and all(e["gcpServiceAccount"] != gsa for e in entries):
                problems.append(f"{where}: {label}: {WI_ANNOTATION} {gsa}가 workload-identities.json의 gcpServiceAccount와 다릅니다(SC-NODE-4)")
        elif kind in RBAC_KINDS:
            if yaml is not None:
                try:
                    obj = yaml.safe_load(doc)
                except yaml.YAMLError as e:
                    problems.append(f"{where}: {label}: YAML을 풀지 못했습니다({str(e).splitlines()[0]})")
                    obj = None
                if isinstance(obj, dict):
                    pairs["rbac"].append((where, obj))
        elif kind == "Secret" and re.search(r"^type:\s*[\"']?kubernetes\.io/service-account-token", doc, re.MULTILINE):
            problems.append(f"{where}: {label}: 서비스 계정 토큰 Secret은 쓰지 않습니다(오래 가는 토큰, projected 토큰으로만, SC-NODE-6)")
        elif kind == "PodDisruptionBudget":
            pairs["pdb"].add((ns, name))
            for value in re.findall(r"[\w./-]+:\s*\"?([\w.-]+)", section(doc, "matchLabels")):
                pairs["pdb"].add((ns, value))
        elif kind == "HorizontalPodAutoscaler":
            scale = section(doc, "scaleTargetRef")
            target = re.search(r"^\s*name:\s*\"?([\w.-]+)", scale, re.MULTILINE)
            target_kind = re.search(r"^\s*kind:\s*\"?([\w.-]+)", scale, re.MULTILINE)
            if target and not target_kind:
                problems.append(f"{where}: {label}: scaleTargetRef.kind가 없습니다(Deployment·StatefulSet·Rollout, 짝을 종류까지 맞춤)")
            elif target:
                pairs["hpa"].add((ns, target_kind.group(1), target.group(1)))
            m = re.search(r"^\s+minReplicas:\s*(\d+)", doc, re.MULTILINE)
            if not m or int(m.group(1)) < MIN_REPLICAS:
                found = m.group(1) if m else "없음(기본 1)"
                problems.append(f"{where}: {label}: minReplicas {found}는 {MIN_REPLICAS} 이상이어야 합니다(AZ 하나를 잃어도 버티는 수)")
        elif kind == "Service":
            m = re.search(r"^\s+type:\s*\"?(NodePort|LoadBalancer)\b", doc, re.MULTILINE)
            if m:
                problems.append(f"{where}: {label}: type {m.group(1)}는 쓰지 않습니다(ClusterIP, 바깥은 라우터·Gateway만)")
        elif kind == "Namespace":
            allowed = "restricted|privileged" if name == PRIV_NAMESPACE else "restricted"  # SC-PRIV-1
            if not re.search(rf"pod-security\.kubernetes\.io/enforce:\s*\"?({allowed})\"?", doc):
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
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(os.environ.get("MOOKKO_PRODUCT_ROOT") or ".").resolve()
    problems: list[str] = []
    counts = {"dockerfile": 0, "compose": 0, "kubernetes": 0}
    namespaces: dict[str, str] = {}
    deny: set[str] = set()
    pairs: dict[str, dict] = {"workloads": {}, "hpa": set(), "pdb": set(), "refs": set(), "ref_from": {}, "rbac": []}
    sec = load_security(root, problems)
    for kind, path, rel in files(root):
        counts[kind] += 1
        text = path.read_text(encoding="utf-8")
        if kind == "kubernetes":
            check_kubernetes(rel.as_posix(), text, problems, namespaces, deny, pairs, sec)
        elif kind == "dockerfile":
            check_dockerfile(rel.as_posix(), text, problems, sec)
        else:
            check_compose(rel.as_posix(), text, problems, sec)
    for key, (where, label) in sorted(pairs["ref_from"].items()):
        if key not in pairs["workloads"]:
            problems.append(f"{where}: {label}: workloadRef가 가리키는 Deployment {key[2]}(네임스페이스 {key[0]})가 저장소에 없습니다")
    for key, (where, label) in sorted(pairs["workloads"].items()):
        if key in pairs["refs"]:
            continue  # Argo Rollout이 workloadRef로 가리키는 Deployment(종류까지 같을 때만): 짝은 Rollout이 가짐
        if key not in pairs["hpa"]:
            problems.append(f"{where}: {label}에 짝 HorizontalPodAutoscaler(scaleTargetRef kind: {key[1]}, name: {key[2]})가 없습니다")
        if (key[0], key[2]) not in pairs["pdb"]:
            problems.append(f"{where}: {label}에 짝 PodDisruptionBudget이 없습니다")
    for ns, where in sorted(namespaces.items()):
        if ns not in deny:
            problems.append(f"{where}: Namespace {ns}에 기본 차단 NetworkPolicy(podSelector: {{}}, Ingress·Egress, 허용 규칙 없음)가 없습니다")
    check_rbac(sec, pairs["rbac"], problems)
    warnings = missing_registers(sec, sum(counts.values()), problems)
    for p in problems:
        print(p)
    for w in warnings:
        print(f"경고: {w}")
    if problems:
        print(f"container check failed ({len(problems)} problems)")
        return 1
    print(
        f"container check passed ({counts['dockerfile']} Dockerfiles, {counts['compose']} compose files, "
        f"{counts['kubernetes']} Kubernetes manifests, security registers {sum(sec.get(k) is not None for k in REGISTERS)}/{len(REGISTERS)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""하네스 검사 스크립트의 표본 시험 (tools.md: 새 검사는 잡아야 할 표본과 통과시켜야 할 표본으로 시험).

ci/fixtures/<검사>/{good,bad}/ 아래 표본을 임시 저장소로 복사해 검사를 돌린다. 표본 파일은 이름 끝에 `.txt`를
붙여 두어(예: a.sh.txt) 저장소 자체 검사가 표본을 실제 파일로 읽지 않게 하고, 복사할 때 `.txt`를 뗀다.
- good: 종료 코드 0
- bad: 종료 코드 1이고 문제 줄 수가 EXPECTED_BAD와 같음(검사가 잡는 개수가 줄면 실패)
임시 폴더는 $TMPDIR/mookko-test/rustdev/<실행>/에 만들고, 이 시험이 성공하면 지우고 실패하면 남긴다.
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]  # 하네스 저장소 최상위
FIXTURES = HARNESS / "ci" / "fixtures"
CHECKS = {
    "dev-exposure": HARNESS / "ci" / "check-dev-exposure.py",
    "acceptance": HARNESS / "ci" / "check-acceptance.py",
    "file-size": HARNESS / "ci" / "check-file-size.py",
    "engine-reuse": HARNESS / "ci" / "check-engine-reuse.py",
    "endpoints": HARNESS / "ci" / "check-no-hardcoded-endpoints.py",
    "lint-escapes": HARNESS / "ci" / "check-lint-escapes.py",
    "waivers": HARNESS / "ci" / "check-waivers.py",
    "tempdirs": HARNESS / "ci" / "check-test-tempdirs.py",
    "boundaries": HARNESS / "ci" / "check-boundaries.py",
    "stack": HARNESS / "ci" / "check-stack.py",
    "forbid-unsafe": HARNESS / "ci" / "check-forbid-unsafe.py",
    "systemd-units": HARNESS / "ci" / "check-systemd-units.py",
    "containers": HARNESS / "ci" / "check-containers.py",
    "containers-sec": HARNESS / "ci" / "check-containers.py",
    "vuln-register": HARNESS / "ci" / "check-vuln-register.py",
    "security-reviews": HARNESS / "ci" / "check-security-reviews.py",
    "design-sources": HARNESS / "ci" / "check-design-sources.py",
    "hardcoded": HARNESS / "ci" / "check-hardcoded-values.py",
    "hardcoded-warn": HARNESS / "ci" / "check-hardcoded-values.py",
    "test-time": HARNESS / "ci" / "check-test-time.py",
    "prr": HARNESS / "ci" / "check-prr.py",
    "production-config": HARNESS / "ci" / "check-production-config.py",
    "harness-copies": HARNESS / "ci" / "check-harness-copies.py",
    "folder-layout": HARNESS / "ci" / "check-folder-layout.py",
}
# cargo metadata로 판정하는 검사는 같은 작은 작업 공간 표본(cargo-ws)을 함께 쓴다. 복사한 뒤 cargo generate-lockfile --offline.
FIXTURE_DIR = {"boundaries": "cargo-ws", "stack": "cargo-ws", "forbid-unsafe": "cargo-ws"}
# cargo-ws bad:
#   boundaries: service s → adapter a1 1, adapter a1 → adapter a2 2(층 허용·어댑터끼리), crates/ 밖 tools/x 1,
#     인수 시험 acceptance/bad → service s 1(엔진만 허용). good: acceptance/ok → engine e.
#   stack: service s → `hyper` 1, 이름에 rust(패키지 rusty-svc·대상 rusty_svc) 2, web vue 1, yarn.lock 1, pnpm-lock 없음 1.
#   forbid-unsafe: tools/x lib 1, s의 tests/t.rs 1.
# containers bad: Dockerfile 5(다이제스트 없음·latest·비밀 ENV·원격 ADD·USER root), compose 14(필수 칸 없음 5, 다이제스트 없는 image, privileged, host 네트워크, seccomp unconfined, docker.sock, cap_add, user root, 주소 없는 포트, 0.0.0.0 포트).
#   등록부 다섯 없음 5(workload-identities 더함)(node-pools·privileged-allowlist·api-clients는 늘, image-registries는 매니페스트가 있으면). Rollout workloadRef: 대상 Deployment 없음 1·replicas 2 1(mookko-rust-qa 11-04 추가 2).
#   짝을 (ns, 종류, 이름)으로(N3): 같은 이름 Rollout same이 대상 없음 1·짝 HPA 없음 1·PDB 없음 1, bad2 HPA 둘에 scaleTargetRef.kind 없음 2
#   그래서 side·roll 짝 HPA 없음 2(합 70). good은 등록부 셋(풀·특권 빈 목록, 표본 레지스트리), workloadRef Rollout(대상 Deployment·HPA·PDB 있음).
#   Kubernetes 38(bad2: 사이드카 권한 상승 2·initContainer 쓰기 루트 2·Rollout 흐름 모양 1·칸 3·hostPort 1·모르는 종류 1·List 1, 짝 HPA·PDB 없음 2, 멀티 AZ 3: zone 분산 없음·replicas 2·HPA minReplicas 없음, Namespace 라벨 없음·기본 차단 없음 2, Deployment 필수 칸 6, 금지 6(hostNetwork·runAsUser 0·Unconfined·add·secretKeyRef·hostPath),
#   컨테이너 5(다이제스트·limits cpu·memory·probe 둘), Service NodePort 1, StorageClass Delete 1, PV Retain 없음 1).
#   good: 한 줄 맵 resources, 운영툴 배포기 주석 예외, Job은 probe 없어도 됨.
# containers-sec bad(보안 등록부 docs/policy/ 셋이 있음): 다른 네임스페이스가 control 풀 1, control 네임스페이스인데 required
#   nodeAffinity 없음 1, untrusted인데 gvisor 없음 1·secret 볼륨 1·serviceAccountName 1, untrusted가 sandbox 네임스페이스 밖 1,
#   mookko-security인데 등록 안 된 이미지의 privileged 1, 바깥 레지스트리 image 1·Dockerfile FROM 1, 등록부 빠진 칸 1,
#   `/`로 안 끝나는 레지스트리 접두어 1, 흐름 모양 라벨의 untrusted(gvisor 없음) 1(보안 규칙은 YAML을 풀어 읽어 흐름 모양
#   tolerations도 읽음), mookko-security(daemonSetNamespaces)라도 DaemonSet이 아닌 Job의
#   `mookko.io/pool` Exists toleration은 그 key의 풀마다 1(control·keys 2), 합 14. api-client 표시가 있지만 등록 없음 1, 등록됐지만 토큰 만료 7200초 1,
#   키 없는 Exists toleration 1(N2, 어디서나 금지), 표시 없이 projected 토큰 1·등록 SA를 다른 워크로드가 씀 1(N1), automount true 1(트리),
#   service-account-token Secret 1, 등록 안 된 이미지 DaemonSet이 전용 풀 2,
#   antiAffinity 없는 mookko-staff-gate 1, 등록 SA Role이 rules 넘음 2(secrets·와일드카드), scope namespace인데 ClusterRoleBinding 1·
#   묶은 ClusterRole 없음 1, Workload Identity: 등록 안 된 워크로드가 WI SA 씀 1·SA 주석 값 다름 1·주석 SA 등록 없음 1,
#   default SA 등록 1, 옛 칸 serviceAccount 1, labelSelector 없는 podAntiAffinity 1, 등록 밖 SA에 묶기 2(ServiceAccount·User 주체),
#   서비스 계정 묶음 Group 1, aggregationRule 1, nonResourceURLs 1(mookko-rust-qa 추가 5),
#   default SA WI 주석 1, 권한 넓히는 권한 3(secrets·rolebindings create·impersonate, 보안 755f466),
#   bindNamespaces 밖 RoleBinding 1(9j 결정),
#   권한 넓히기 4(roles bind·escalate, clusterroles update, serviceaccounts create)·system:authenticated Group 1(추가 6 ⑤),
#   보안 fb18ab2 넓힘 6(pods create·deployments patch·webhook update·CRD create·signers approve·persistentvolumes create),
#   platform-controller(보안 730d41a) control 풀 밖 1·allowedEscalations 밖 등록 1·workload에 allowedEscalations 1·class 값 1·묶인 Role 밖 1,
#   platform-controller 적지 않은 하위 자원 2(등록 pods/exec·묶인 Role pods/attach, 보안 c50f515 확인), 합 62. good: staff-gate namespaceSelector podAntiAffinity.
#   good: Falco DaemonSet은 전용 풀 taint를 받음, 운영툴 배포기는 등록·projected 토큰 3600초. 보안 규칙 표본은 PyYAML이 있는 Linux python3에서만 돈다(하네스 CI).
#   good: 자기 풀 required affinity, 등록 이미지 Falco(privileged·hostPID·hostPath), untrusted gvisor 작업자, 빌드 단계 별칭 FROM.
# security-reviews bad: 빠진 칸 1, verdict 1, 날짜 1(만료·기록 없는 절은 경고만, --l4에서 실패). good: 절 sha256 맞음(끝 빈 줄 뺌),
#   기록 없는 security:reviewed 절은 경고만.
# vuln-register bad(보안 담당 기준 ee18cf1): 빠진 칸 1, id 겹침 1, 30일 넘음(결정 없음) 1, 결정일부터 30일 넘음 1, 기한 지남 1,
#   날짜 모양 1, 연 날보다 먼저 닫음 1, 받지 않는 kind 1, 열린 항목이 detect만 1, 빈 action 1, reviewBy 범위 밖 1, fixedIn 없음 1,
#   객체 아님 1, id 꼴 1, affects 접두어 1(합 15, reviewBy 지남은 경고만). good: 열린 항목, 닫은 GHSA 항목(detect만이어도 닫았으면 됨),
#   userDecision으로 30일을 넘긴 항목. 기준 판 대조는 표본 폴더가 git 최상위가 아니라 건너뜀.
# design-sources bad(enforce true): 결정 표에 표준 출처 칸 없음 1, 빈 칸 1, "-" 1, TBD 1(넓힌 모양 ID·정한 값 표는 경고만). good: 출처·해당 없음, 결정 아닌 표는 안 봄.
# hardcoded bad(enforce true): DUR 1, NUM 3(비교식·호출 인자·const fn 몸통), INC 1(엔진 시험이 서비스 파일), PATH 3(드라이브 문자 경로·/mnt 드라이브·/home 사용자), 기준보다 줄어듦 1.
#   good: const 안 Duration·숫자, 문자열(여러 줄 포함)·문자·99, 시험 모듈, 기준 안 개수, crate 안 include, 상대 경로.
# hardcoded-warn(enforce false): bad 기준보다 늘어 경고 모드여도 실패(그 파일 줄 2), good 줄어듦은 경고만.
# test-time bad(enforce true): tests의 thread::sleep 1·tokio sleep(멈추지 않은 파일) 1·SystemTime::now 1, src #[cfg(test)]의 Utc::now 1, 기준보다 줄어듦 1.
#   good: start_paused 파일의 tokio sleep, 주석·문자열, 제품 코드의 SystemTime::now, 기준 안 개수.
# production-config bad: 세션 절대·유휴 2, rpc staffRecentMfa 없음 1, 파일 KEK 1, devLocal 1, 평문 HTTP 1, tls disable 1, requireMfa 없음 1, 덮어쓰기의 파일 객체 저장소 1·requireMfa false 1. good: 운영 값, development 설정은 안 봄. requireMfa 둘은 엔진 칸이 생길 때까지 경고(QE-SEC-3)라 세지 않음(10→8).
# prr bad(enforce true, qa-services T1~T4): 문서 없음 1, 항목 줄 없음 1, 빈 칸 2(빈 칸·"-"), 필수 낱말 없음 2(SLO·SLI 넷, 백업·복구 둘),
#   경보: runbook 링크 없음 1·빈 칸(소진율 창) 1·증상/원인 값 1·링크 대상 없음 1, 사고 대응 훈련 열 없음 1, 정기 훈련·시험 표 없음 1.
#   good: 미정 칸은 낱말을 보지 않음, 앵커 붙은 링크, 열 이름으로 읽는 표(틀의 '적을 것' 열 있어도 됨), 두 훈련 표.
# systemd-units bad: User=root 1, NoNewPrivileges 없음 1, ExecStart=+ 1, .socket 1. good은 mookko-links-maintain.service 사본.
# lint-escapes bad: src #[allow] 1, #![allow] 1, cfg_attr(…allow) 1, tests의 정해진 머리줄이 아닌 allow 1, web eslint-disable 1,
#   acceptance/ 아래 #[allow] 1.
#   good: tests 머리줄, 등록부에 오른 예외.
# tempdirs bad: join이 mookko-test 아님 1, temp_dir 단독 1, panicking 없는 Drop 1, mookko-test 밖 변수 1, "$HOME/target" 1, /tmp/* 1, 정의 없는 변수 1.
# waivers bad: 빠진 칸 1, id 겹침 1, 만료 1, 180일 넘음 1, 없는 경로 1, adr 문서 없음 1. 날짜는 @@TODAY±N@@로 실행 날 기준.
# acceptance bad: enforce인데 기록 없음 1, 깨진 JSON 1, 다른 service 1, 짧은 commit 1, passed 형 틀림 1, 파일 이름 틀림 1,
#   services.json에 없는 runs 폴더 1, enforce 서비스의 가장 최근 기록이 실패(앞 기록은 통과) 1.
# file-size bad: src 601줄 1, 시험 모듈 뒤 코드까지 650줄 1, 600줄 이하인데 예외가 남음 1, 예외의 파일이 없음 1(tests/ 900줄은 세지 않음).
#   good: `#[cfg(test)] mod t;`가 가리키는 900줄 t.rs는 세지 않음, src/tests/ 모듈 폴더는 셈.
# engine-reuse bad: C1 상수 1, C2 SystemClock 1, C3 is_identifier 1, C4 prev_hash 1, 복사본이 없는데 남은 예외 1,
#   넓힌 모양 4(SystemTime::now, "recent_mfa_required", Hmac<, fn rw() -> TxOptions).
# endpoints bad: IPv4 1, localhost 1, URL 1, host:port 1, Ipv4Addr::LOCALHOST 2(생성자·localhost).
#   good: 판 문자열 "1.2.3.4.5"·"v1.0.0.1", 300으로 시작하는 넷 덩어리, 주석 줄은 잡지 않음.
EXPECTED_BAD = {
    "dev-exposure": 15,
    "acceptance": 8,
    "file-size": 4,
    "engine-reuse": 9,
    "endpoints": 6,
    "lint-escapes": 6,
    "waivers": 6,
    "tempdirs": 7,
    "boundaries": 5,
    "stack": 6,
    "forbid-unsafe": 2,
    "systemd-units": 4,
    "containers": 71,
    "containers-sec": 62,
    "vuln-register": 15,
    "security-reviews": 3,
    "design-sources": 4,
    "hardcoded": 9,
    "hardcoded-warn": 2,
    "test-time": 5,
    "prr": 12,
    "production-config": 8,
    "harness-copies": 5,
    "folder-layout": 5,
}
# harness-copies bad: gates.md 다름 1, gates.json 정본 없음 1, 규약 b 사본 없음 1, 규약 c 정본에 없음 1, 스킬 다름 1.
#   good: 같은 사본, 하네스 skills/README.md는 옮기지 않음. 하네스 쪽은 표본 안 harness/(EXTRA_ARGS).
# folder-layout bad: 최상위 stray.py 1, 정하지 않은 tools/ 1, rules/ 안내 없음 1, rules/x.py 종류 1, config/a.yaml 종류 1.
# 표본 폴더 뒤에 붙이는 인자(표본 안 경로). check-all이 내보낸 MOOKKO_HARNESS_DIR 대신 표본 안 하네스를 쓰게 함.
EXTRA_ARGS = {"harness-copies": ["harness"]}
PROBLEM_LINE = re.compile(r"^(?:\s*-\s+)?\S+:\d+: ")
# 줄 번호 없이 `  - …`로 문제를 내는 검사
_DASH = re.compile(r"^\s+-\s+\S")
PROBLEM_LINE_BY_CHECK = {k: _DASH for k in ("waivers", "boundaries", "stack", "forbid-unsafe", "systemd-units")}
DATE_TOKEN = re.compile(r"@@TODAY([+-]\d+)@@")


def materialize(src: Path, dest: Path) -> None:
    """`.txt`를 떼어 복사하고, 글 안의 @@TODAY±N@@을 실행 날 기준 날짜로 바꾼다(기한 표본이 날짜가 지나며 썩지 않게)."""
    today = datetime.date.today()
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        name = rel.name[:-4] if rel.name.endswith(".txt") else rel.name
        target = dest / rel.parent / name
        target.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text(encoding="utf-8")
        text = DATE_TOKEN.sub(lambda m: (today + datetime.timedelta(days=int(m.group(1)))).isoformat(), text)
        target.write_text(text, encoding="utf-8")


def run(name: str, check: Path, repo: Path) -> tuple[int, list[str]]:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(check), str(repo), *(str(repo / a) for a in EXTRA_ARGS.get(name, []))],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    pattern = PROBLEM_LINE_BY_CHECK.get(name, PROBLEM_LINE)
    lines = [line for line in result.stdout.splitlines() if pattern.match(line)]
    return result.returncode, lines


def main() -> int:
    base = Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "mookko-test" / "rustdev"
    base.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="ci-checks-", dir=base))
    failures: list[str] = []
    for name, check in CHECKS.items():
        for kind in ("good", "bad"):
            repo = run_dir / name / kind
            materialize(FIXTURES / FIXTURE_DIR.get(name, name) / kind, repo)
            if (repo / "Cargo.toml").exists():
                # 길 의존만 있는 작은 작업 공간이라 인터넷 없이 lock을 만든다(검사가 --locked로 돈다).
                subprocess.run(["cargo", "generate-lockfile", "--offline", "--quiet"], cwd=repo, check=True)
            code, lines = run(name, check, repo)
            if kind == "good" and code != 0:
                failures.append(f"ci/fixtures/{name}/good:1: 통과해야 할 표본이 걸림(rc={code}): {lines}")
            if kind == "bad" and (code != 1 or len(lines) != EXPECTED_BAD[name]):
                failures.append(
                    f"ci/fixtures/{name}/bad:1: 잡아야 할 표본 {EXPECTED_BAD[name]}건 중 {len(lines)}건(rc={code})"
                    + "".join(f"\n  {line}" for line in lines)
                )
    # git 기록을 보는 검사(check-owner-paths)와 메모리 관문은 임시 git 저장소·설정으로 시험(test_git_checks.py)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import test_git_checks  # noqa: E402

    failures += test_git_checks.run_all(run_dir / "git")
    for failure in failures:
        print(failure)
    if failures:
        print(f"ci check samples failed; kept {run_dir}")
        return 1
    shutil.rmtree(run_dir)
    print(f"ci check samples passed ({len(CHECKS)} checks, git·메모리 표본 포함)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

---
name: mookko-security
description: MooKKo 보안 규약(플랫폼·운영). 운영 매니페스트(deploy/·Kubernetes YAML)·IaC·노드 풀·네임스페이스·RBAC·Workload Identity·NetworkPolicy·런타임 감지 규칙·사고 대응·취약점 기록·비밀값·키·인증서 설계를 쓰거나 고치거나 리뷰할 때 반드시 먼저 읽는다. 신뢰 등급별 노드 풀(키·운영툴·Argo CD 전용), 바깥 입력은 gVisor 샌드박스, 특권은 mookko-security 네임스페이스 등록 이미지만, Falco·Tetragon 출시 전 필수, 사고 대응 절차서 하나, 패치 지연 완화 기록부, 보안 설계 검토 줄.
---

# MooKKo 보안 규약 (요약)

정본은 `docs/policy/conventions/security.md`(규칙 번호 SC-*), 왜 그런지는 `docs/architecture/security.md`·`incident-response.md`·`host-security.md` §1.1·§7.1. 관문은 SEC-02(피해 범위·격리)·SEC-03(탐지·대응)·SEC-04(취약점·패치 지연)이고, 앱 보안(인증·세션·입력·쿠키·ASVS·STRIDE)은 SEC-01과 언어별 규약이 본다. 워크로드 기본 위생(PSS restricted·읽기 전용 루트·NetworkPolicy 기본 차단·자원 상한·서명 확인)은 HOST-01·`deploy-containers.md` §3 그대로 지킨다.

보안 담당은 기준을 정하고 검토만 한다. 구현은 각 담당이고, 공용 보안 기능(MFA·상호 TLS·KMS·비밀값·로그인·감사 원장)은 엔진에만 만든다.

## 매니페스트를 쓸 때

- 풀 고르기(SC-NODE-1·2): 키 DB → `keys`, 운영툴·Argo CD·Argo Rollouts·cert-manager·External Secrets → `control`, 돈 DB → `db-money`, 뗀 일반 DB → `db-general`, 바깥 입력 작업자 → `sandbox`, 나머지 → `general`. 전용 풀의 워크로드는 `requiredDuringSchedulingIgnoredDuringExecution` nodeAffinity로 자기 풀만 고르고 toleration을 단다. **다른 네임스페이스가 그 풀의 toleration·nodeSelector를 쓰면 안 된다**(admission·검사가 막음).
- 바깥 입력(SC-SBX-1~3): 바깥이 고른 바이트를 파서(이미지·영상·문서·압축·폰트)로 다루거나 바깥이 고른 주소로 나가면 `mookko.io/input: untrusted` 라벨 + `runtimeClassName: gvisor` + `sandbox` 풀. 그 일만 하는 Deployment로 떼고(엔진 포트의 원격 어댑터), 비밀값 파일·DB·Workload Identity 권한·SA 토큰 없음, 나가기는 나가기 프록시만(사설·링크 로컬·`169.254.169.254`·내부 DNS 거부).
- 특권(SC-PRIV-1): `privileged`·`hostPID`·`hostNetwork`·`hostPath`가 필요한 것은 `mookko-security` 네임스페이스의 `docs/policy/privileged-allowlist.json` 등록 이미지(Falco·Tetragon 등)뿐.
- 이미지(SC-VULN-4): 제3자 이미지도 우리 레지스트리로 가져와 검사·서명한 다이제스트만.
- Kubernetes API 토큰(SC-NODE-6): 모두 `automountServiceAccountToken: false`. API를 부르는 워크로드는 `docs/policy/api-clients.json`에 등록된 것만, 등록한 SA + projected 토큰(≤ 3600초)으로. 모든 노드에 떠야 하는 DaemonSet은 `mookko-security`(daemonSetNamespaces)에서만.
- 서비스 계정(SC-NODE-4): Kubernetes SA 하나 = Workload Identity 주체 하나, 실제로 부르는 권한만. 여러 서비스가 IAM 서비스 계정을 같이 쓰지 않는다.

## 노드·클러스터·IaC를 쓸 때 (SC-NODE-3·5)

풀마다 전용 노드 서비스 계정(`roles/container.defaultNodeServiceAccount` + 레지스트리 읽기), Workload Identity(`GKE_METADATA`), Shielded·보안 부팅·무결성 모니터링, 사설 노드, 자동 업그레이드·복구, kubelet 읽기 전용 포트 끔. 제어부는 사설 끝점 + 승인된 네트워크. etcd 비밀값 애플리케이션 계층 암호화, 디스크 CMEK. Compute 기본 서비스 계정·레거시 ABAC·기본 인증·대시보드 금지. 사람의 kubectl·콘솔 쓰기는 비상 경로뿐.

## 감지 규칙을 쓸 때 (SC-DET-*)

Falco는 모든 풀, Tetragon은 `keys`·`control`(처음 2주 감사만, 그 뒤 허용 목록 밖 실행 막기). 규칙마다 ATT&CK 기법 번호·등급(SEV1~3-SEC)·runbook 링크. 끄기·약하게 바꾸기는 보안 담당 확인 + 두 사람 승인. 오탐 예외는 이미지·프로세스·경로 단위로 좁게, 이유·만료일. 에이전트·감사 로그 끊김은 그 자체가 경보. 감사 기록에 `개인` 이상 값·비밀값을 넣지 않는다. 예외는 접속기록 칸 둘뿐이다. 직원·서비스 계정 주체의 식별자와 접속지 IP는 그대로 두고, 바깥 주체는 KeyedHasher 값 + 경보로 남긴다(SC-DET-4).

## 사고·비밀값 설계 (SC-IR-*)

등급·역할·플레이북은 `incident-response.md` 하나(서비스 runbook은 가리키기만). 새 비밀값·키·인증서를 들이면 그 설계서에 "탈취 때 교체 방법·담당·시간"을 적고 incident-response §5.1 교체 표에 더한다. 출시 전 탁상 훈련 1회 + 노드 격리·버리기·교체 기술 훈련 1회 기록.

## 취약점·패치 지연 (SC-VULN-*)

KEV·실제 공격 48시간, 치명 7일을 벤더 때문에 못 맞추면 기한 절반 전에 `docs/policy/vuln-register.json` 항목(`id`·`affects`·`exposure`·`mitigations`·`opened`·`reviewBy`·`expires` 최대 30일·`owner`). 순서: 기록 → 노출 끊기 → 격리(gVisor 풀) → 감지 강화 → 다른 노드 이미지(두 사람 승인) → 30일 넘으면 사용자 결정. 기다리기만 하는 항목은 받지 않는다. 고친 판이 나오면 기한을 다시 세고 `closed`로 닫는다(지우지 않음). 취약점 검사 무시(cargo audit·cargo deny·pnpm audit·Trivy)는 심각도와 상관없이 기록부의 열린 항목(`advisories`에 권고 id, `affects`는 `crate:`·`npm:`)과 짝이어야 하고, 권고 id 하나씩만 적는다. "빌드 안 됨"이 근거면 `deny.toml` bans 같은 장치로 묶는다(SC-VULN-5).

## 보안 설계 검토 (SC-REV-*)

새 바깥 입구·바깥 주소 가져오기, 돈·키·인증·MFA·세션·비밀값·서명, 풀·네임스페이스·RBAC·Workload Identity·NetworkPolicy 넓히기, 특권·샌드박스 예외·감지 규칙 끄기는 설계서에 `security:reviewed <날짜> <세션>` 줄이 있어야 출시 관문(L4)을 넘는다. 개발·통합은 막지 않는다. 보안 담당은 한 영업일 안에 검토한다.

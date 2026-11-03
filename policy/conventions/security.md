# 보안 규약 (플랫폼·운영 — 노드 풀·샌드박스·감지·대응·취약점)

대상: 운영 매니페스트(`deploy/`·Kubernetes YAML·Helm·Kustomize), IaC(OpenTofu), 노드·클러스터 설정, 런타임 감지 규칙, 사고 대응·취약점 기록, 보안에 민감한 설계서. 왜 그렇게 하는지와 운영 모양은 제품 보안 정본 [`docs/architecture/security.md`](../../architecture/security.md)·[`incident-response.md`](../../architecture/incident-response.md)·[`host-security.md`](../../architecture/host-security.md) §1.1·§7.1입니다. 관문은 SEC-02(피해 범위·격리)·SEC-03(탐지·대응)·SEC-04(취약점·패치 지연)이고, 앱·기능 보안(인증·세션·입력·쿠키, ASVS·STRIDE)은 SEC-01과 언어별 규약(rust.md·frontend.md·sql.md)이 봅니다.

담당: 보안 전문 담당(기준·설계 검토). 강제는 하네스, 구현은 각 담당(엔진·모니터링·로그·운영툴·DB·서비스)입니다. 규칙을 약하게 바꾸는 것(예외 넓히기·기한 늘리기·검사 끄기)은 사용자 결정 없이는 `fail`입니다.

강제 표시는 [README.md](README.md) › 강제 표시. **[검사]** 중 아직 없는 것은 "(하네스에 요청)"으로 적었고, 그동안은 **[QA]**로 판정합니다.

## 0. 등록부는 닫힌 쪽 (QA 2026-11-04 ①, 보안 담당 결정)

- SC-REG-1 등록부 `docs/policy/node-pools.json`·`privileged-allowlist.json`·`vuln-register.json`은 제품에 **늘 있어야** 한다(빈 목록이어도). 파일이 없으면 검사가 꺼지는 대신 **실패**한다. `image-registries.json`은 레지스트리가 정해지기 전이라, 저장소에 Dockerfile·Compose·Kubernetes 이미지가 하나라도 있는데 이 파일이 없으면 실패한다. **[검사]** `ci/check-containers.py`·`ci/check-vuln-register.py`(하네스, 제품에 빈 등록부가 들어간 뒤 같은 묶음에서 켬)
- SC-REG-2 빈 등록부는 "아무것도 허용하지 않음"이다. 전용 풀 네임스페이스에 등록되지 않은 워크로드는 그 풀을 고를 수 없다. 특권 이미지가 비면 특권 컨테이너는 하나도 받지 않는다. 등록부를 고치는 것은 보안 담당이다(owners.json). 다른 담당은 보안 담당에게 요청한다.

## 1. 노드 풀·피해 범위 (SEC-02)

- SC-NODE-1 신뢰 등급이 다른 워크로드를 같은 노드에 두지 않는다. 풀은 `system`·`general`·`sandbox`·`control`·`keys`·`db-money`·`db-general`(일반 DB를 뗀 뒤, security.md §2.2). 키 DB는 `keys`, 운영툴·Argo CD·Argo Rollouts·cert-manager·External Secrets는 `control`, 돈 DB는 `db-money`. 새 풀은 security.md를 먼저 고친다. **[QA]**(어느 워크로드가 어느 풀인지) **[검사]** SC-NODE-2와 같은 `ci/check-containers.py` 대응표 검사(네임스페이스 → 풀)
- SC-NODE-2 `control`·`keys`·`db-money`·`db-general`·`sandbox` 풀의 toleration·nodeSelector·nodeAffinity는 그 풀에 정해진 네임스페이스만 쓴다. 정해진 네임스페이스의 워크로드는 반드시 `requiredDuringScheduling…` nodeAffinity로 자기 풀만 고른다(taint만으로는 막히지 않음). 클러스터에서는 ValidatingAdmissionPolicy로 다시 막는다. 대응표는 제품 `docs/policy/node-pools.json`(`{"schema":1,"pools":[{"name","key","value","namespaces":[…]}]}`, `sandbox`는 key `sandbox.gke.io/runtime`·value `gvisor`). **[검사]** `ci/check-containers.py` (정책 파일이 있을 때만 켜짐, bacb580)
- SC-NODE-3 노드 풀마다 전용 노드 서비스 계정(최소 역할 `roles/container.defaultNodeServiceAccount` + 레지스트리 읽기), Workload Identity(`GKE_METADATA`), Shielded·보안 부팅·무결성 모니터링, 사설 노드, 자동 업그레이드·자동 복구, kubelet 읽기 전용 포트 끔. Compute 기본 서비스 계정 금지. **[검사]** OpenTofu plan 정책(IaC 저장소가 생기면, 하네스에 요청) **[QA]**
- SC-NODE-4 Kubernetes 서비스 계정 하나에 Workload Identity 주체 하나, 권한은 그 서비스가 실제로 부르는 것만. 여러 서비스가 한 IAM 서비스 계정을 함께 쓰지 않는다. **[QA]**
- SC-NODE-5 제어부는 사설 끝점 + 승인된 네트워크. 사람의 kubectl·콘솔 쓰기는 비상 경로(두 사람·경보·감사)뿐. **[QA]**

## 2. 바깥 입력 샌드박스 (SEC-02)

- SC-SBX-1 바깥이 고른 바이트를 복잡한 파서(이미지·영상·문서·압축·폰트)로 다루는 Pod, 바깥이 고른 주소로 나가는 연결을 여는 Pod는 `runtimeClassName: gvisor`로 `sandbox` 풀에서 돈다. 그 Deployment에 라벨 `mookko.io/input: untrusted`를 단다. 검사는 YAML을 실제로 풀어 라벨을 읽는다(흐름 스타일 `{mookko.io/input: untrusted}`·따옴표도 같게 봄, QA ③). **[검사]** `ci/check-containers.py`(라벨이 있으면 `runtimeClassName: gvisor` + `sandbox` 풀 네임스페이스, node-pools.json이 있을 때) **[QA]**(라벨을 달아야 할 Deployment에 빠졌는지)
- SC-SBX-2 샌드박스 대상 일은 그 일만 하는 Deployment로 뗀다(서비스 본체에 파서·가져오기를 두지 않음). 엔진 포트(예: `ImageSanitizer`)의 원격 어댑터로 부른다. **[QA]**
- SC-SBX-3 샌드박스 작업자는 비밀값 파일·DB 접속·Workload Identity 권한·Kubernetes 서비스 계정 토큰을 갖지 않는다. 나가기는 NetworkPolicy로 막고, 바깥 주소 가져오기는 나가기 프록시만(사설·링크 로컬·메타데이터·내부 DNS 거부, 이름 풀이 뒤 주소 다시 확인). **[검사]** `ci/check-containers.py`(라벨 있는 워크로드에 secret 볼륨·serviceAccountToken·`default` 밖 `serviceAccountName`·API 예외 주석이 있으면 실패) **[QA]**
- SC-SBX-4 공개 Node.js SSR의 샌드박스 여부는 출시 전 부하 시험 결과로 보안 담당이 정한다(security.md §3.1). 정하기 전에는 샌드박스 없는 판을 라이브에 내지 않는다(L4 `fail`). **[QA]**

## 3. 특권·예외 (SEC-02·SEC-03)

- SC-PRIV-1 PSS `privileged`는 네임스페이스 `mookko-security` 하나만이고, 그 안의 이미지는 제품 `docs/policy/privileged-allowlist.json`(`{"images":[{"image"(다이제스트),"reason","owner","reviewed"}]}`)에 있는 것만. 다른 특권 예외는 없다. 면제는 특권·host 공유·컨테이너 권한 칸뿐이고 이미지·자원·probe·비밀 환경 변수 규칙은 그대로다. **[검사]** `ci/check-containers.py` (정책 파일이 있을 때만 켜짐, bacb580)
- SC-PRIV-2 Binary Authorization·admission 우회(break-glass)와 비상 계정 사용은 사고 선언(SEV2-SEC 이상)과 감사 기록이 짝이다. 훈련은 미리 공지한다. **[QA]**

## 4. 탐지 (SEC-03)

- SC-DET-1 모든 노드 풀에 Falco, `keys`·`control` 풀에 Tetragon. 판·규칙은 설정 저장소에 판으로 두고 Argo CD가 배포한다(host-security §7.1). **[QA]** **[검사]** 매니페스트 존재·풀 덮기(하네스에 요청)
- SC-DET-2 규칙마다 ATT&CK 기법 번호·사고 등급·runbook 링크가 있다. 규칙을 끄거나 약하게 바꾸려면 보안 담당 확인 + 두 사람 승인. 오탐 예외는 이미지·프로세스·경로 단위로 좁게, 이유·만료일과 함께. **[QA]** **[검사]** 규칙 파일 칸 검사(하네스에 요청)
- SC-DET-3 감지 에이전트·감사 로그가 끊기면 그 자체가 경보(dead-man). **[QA]**
- SC-DET-4 감사 로그(Cloud Audit Logs 관리자·데이터 액세스(KMS·Secret Manager), GKE 감사, 런타임 감지)는 로그 서비스 보안 등급으로 모으고 WORM으로 보관한다(법무 확인 전 2년). `개인` 이상 값과 비밀값은 감사 기록에 넣지 않는다(sql.md S-SEC-5와 같음). **예외(접속기록, 보안 담당 2026-11-04)**: 개인정보 안전성 확보조치 기준 제8조의 접속기록 칸, 곧 행위자 식별(`principalEmail`·`principalSubject`)과 접속지(`callerIp`)는 보안 등급 기록에 그대로 둔다. 다만 우리 직원 도메인과 서비스 계정·`system:` 주체만이다. 그 밖의 주체는 이메일 원문 대신 엔진 KeyedHasher 값(같은 주체끼리 묶을 수 있게)을 남기고 경보를 올린다. 접속지 IP는 침해사고 원인 분석에 필요해 주체와 상관없이 둔다. 이 예외 칸은 허용 목록으로만 열고, 조회는 `logs.security` + 최근 MFA + 사건 번호로 한다. **[QA]**

## 5. 대응 (SEC-03)

- SC-IR-1 사고 등급·역할·플레이북은 `incident-response.md` 하나가 정본이다. 서비스 runbook은 그것을 가리키고 따로 등급을 만들지 않는다. PRR-01의 당번·사후 검토도 같은 문서를 본다. **[QA]**
- SC-IR-2 출시 관문(L4) 전에 탁상 훈련 1회 + 노드 격리·버리기·비밀값 교체 기술 훈련 1회(내부 서버 시험 클러스터)의 기록이 있다. 그 뒤 분기마다. **[검사]** `ci/check-prr.py`(`prr.md`의 `## 사고 대응 훈련` 표 `| 훈련 | 날짜 | 기록 |`에 탁상·기술 훈련 줄, 날짜 YYYY-MM-DD, 기록은 저장소 안 링크; prr.json enforce 전에는 경고) **[QA]**
- SC-IR-3 새 비밀값·키·인증서를 들일 때는 "탈취 때 어떻게 바꾸나"(교체 방법·담당·걸리는 시간)를 그 설계서에 함께 적는다. incident-response §5.1 교체 표에 없는 것은 그 표에 더한다. **[QA]**

## 6. 취약점·패치 지연 (SEC-04)

- SC-VULN-1 패치 기한(host-security §1: KEV·실제 공격 48시간, 치명 7일)을 벤더 때문에 못 맞추면 기한의 절반이 지나기 전에 제품 `docs/policy/vuln-register.json`에 항목을 연다: `id`(`CVE-YYYY-N…` 또는 `GHSA-…` 꼴만), `affects`(`pool:`·`image:`·`host:` 접두어), `exposure`(노출 경로 판단), `mitigations`(목록, 항목마다 `{"kind","action"}`), `opened`, `reviewBy`(매일 다시 봄), `expires`(최대 30일), `owner`. **[검사]** `ci/check-vuln-register.py`(check-all: 칸·`expires` ≤ opened+30일·id 겹침, 닫지 않은 항목 `expires`가 지나면 실패·`reviewBy`가 지나면 경고)
  - **기다리기만 막기(QA 2026-11-04 ④)**: `kind`는 `block-exposure`(노출 끊기)·`isolate`(격리·gVisor로 옮김)·`disable-feature`(기능 끄기)·`detect`(감지 강화)·`alt-image`(다른 이미지)만 받는다. 열린 항목에는 `block-exposure`·`isolate`·`disable-feature`·`alt-image` 중 하나 이상이 있어야 한다. `detect`만 있으면 실패다. `action`은 빈 글이 아니다. **[검사]** 위 검사 확장(하네스)
  - **id 바꿔 기한 늘리기 막기(⑤)**: 한 `id`에는 항목이 평생 하나다(닫은 항목도 지우지 않음). 30일을 넘기려면 같은 항목에 `userDecision`(`{"date","ref"}`, 사용자 결정 기록 위치)을 달고 `expires`를 그 날짜부터 최대 30일로 다시 정한다. 기준 브랜치(`foundation/engine`)와 견줘 항목이 사라지거나 `id`·`opened`가 바뀌면 실패다. **[검사]** 위 검사 확장(하네스)
- SC-VULN-2 완화 순서는 host-security §1.1: 기록 → 노출 끊기 → 워크로드 격리 → 감지 강화 → (못 막으면) 다른 이미지 → 30일 넘으면 사용자 결정. 완화 없이 기다리기만 하는 항목은 받지 않는다. **[QA]**
- SC-VULN-3 고친 판이 나오면 그날부터 §1 기한을 다시 세고, 올린 뒤 항목을 닫는다(지우지 않고 `closed`와 날짜). **[QA]**
- SC-VULN-4 기반 이미지·제3자 이미지(Envoy·Argo·CNPG·Falco 등)도 같은 기록부다. 바깥 레지스트리에서 바로 끌지 않고 우리 레지스트리로 가져와 검사·서명 뒤에만 쓴다. **[검사]** `ci/check-containers.py`(Dockerfile FROM·Compose·컨테이너 image가 제품 `docs/policy/image-registries.json` `{"registries":[접두어]}`로 시작, bacb580). 접두어는 `/`로 끝나야 하고 이미지는 그 경로 경계에서 맞아야 한다(`reg.example/a/`가 `reg.example/ab/x`를 받지 않음, QA ②). **[QA]**

## 7. 보안 설계 검토

- SC-REV-1 아래 변경은 설계서·명세에 보안 담당의 검토 줄 `security:reviewed <날짜> <검토 세션>`(또는 `security:changes <날짜> <고칠 점>`)이 있어야 출시 관문(L4)을 넘는다. 개발·통합은 막지 않는다(2차 관문처럼 `warn`). **[QA]**
  - 새 바깥 입구(공개 경로·API·웹훅 받기), 바깥 주소 가져오기
  - 돈·키·인증·MFA·세션·비밀값·서명
  - 노드 풀·네임스페이스·RBAC·Workload Identity·NetworkPolicy 허용 넓히기
  - 특권·샌드박스 예외, 감지 규칙 끄기
- SC-REV-2 보안 담당은 받은 뒤 **한 영업일 안에** 검토하거나 고칠 점을 낸다(qa-design 설계 승인과 같은 기한). **[QA]**

## 8. 표준

판정 기준으로 쓰는 표준과 대조표는 security.md §7입니다: CIS GKE Benchmark, CIS Kubernetes Benchmark, MITRE ATT&CK for Containers, SLSA v1.0, NIST SP 800-61r3·800-40r4, Google IMAG, ISMS-P, 개인정보보호법·정보통신망법(법무 확인 필요 항목은 그렇게 표시). 표준보다 낮게 가려면 설계서에 이유·출처·PM 확인을 적는다(ARCH-01).

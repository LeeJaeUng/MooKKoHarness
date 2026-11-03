# MooKKo QA 관문

> **QA 상태 (2026-11-03)**: 10-29의 "QA 보류"는 끝났습니다. 지금은 분야별 QA 세션 4개가 판정합니다. QA는 통합을 막지 않고 옆에서 판정하며, 그동안 통합된 커밋은 소급해서 판정합니다. 세션 구성은 QAManager가 정합니다.
>
> | 분야 | 세션 | 주로 보는 관문 |
> |---|---|---|
> | 설계서·SQL | qa-design | DBDES-01, FINOPS-01(데이터), PRIV-01(보관·수집), DEPLOY-01(DB 넓히기·좁히기) |
> | 엔진·어댑터·proto | qa-engine | RUST·ASYNC·SEC, REL-01, PERF-01(엔진), DEPLOY-01(proto 호환), XC(시계·저장소 틀·권한) |
> | 서비스·앱 | qa-services | SPEC-01·ACC-01, PRR-01, OPS-01, XC(MFA·이름·감사 원장) |
> | 도구·CI·빌드 | mookko-rust-qa | DEPS-01, CONV-01(T-*), TEST-01, HOST-01, WEB-01, 하네스 검사 결과 대조. check-all은 이 세션만 돌림 |
>
> - **판정 엔진**: 당분간 개발과 QA 모두 Claude입니다(사용자 2026-10-29). 결과마다 "엔진: Claude(모델명), 다른 엔진 아님"이라고 적습니다.
> - **등급 표기**: 바깥에서 아직 뚫리지 않는다는 이유로 높음을 보통으로 내릴 때는 "보통(연결 전 필수: <어떤 연결>)"로 적습니다. 이 표시가 열려 있는 동안 통합 담당은 그 연결 커밋을 통합하지 않습니다.
> - **DBDES-01 설계 승인은 다시 합니다.** 앞으로 스키마를 바꾸는 커밋은 qa-design이 그 설계서를 `design:approved`로 판정한 뒤에 통합합니다. 승인 없이 통합된 설계서 5개(운영툴·모니터링·로그·links·엔진 표)는 고칠 점이 닫히면 그때 승인합니다. 아직 승인되지 않은 설계서에 이관을 더하는 커밋은 판정에서 `fail`이 아니라 "보통(연결 전 필수: 운영 DB에 이관 적용 전)"으로 봅니다. 승인을 기다리느라 개발을 세우지는 않습니다. qa-design은 설계서를 받은 뒤 **한 영업일 안에** 승인하거나 고칠 점을 냅니다(PM 대행 2026-11-03).
> - 자동 검사(lint·시험·deny·audit·경계·주소·스택·규칙 끄기)는 처음부터 줄이지 않았습니다.

목록·적용 경로의 정본은 `gates.json`입니다. QA는 영수증마다 모든 관문을 하나씩 `pass | fail | na | waived`로 판정하고, 후보의 변경 경로에 적용되는 관문은 `na`로 넘길 수 없습니다. `pass`에는 그 관문 경로 안의 파일·줄 근거가 필요합니다. `waived`는 이 저장소의 ADR과 만료일이 있는 예외 등록부 항목이 있어야 합니다(일반 예외는 `docs/policy/waivers.json`, DB S-BND-7은 `docs/policy/db/exceptions.json`, 규칙 끄기는 `lint-exceptions.json`; 기한이 지나면 check-all 실패). 기준은 "가장 높은 수준"입니다(사용자 2026-10-20: 알리페이·알리바바급 속도·보안·안전, 99.99%). 낮은 목표를 임의로 두지 않습니다.

## QA의 목표: 대용량 대기업 서비스처럼 라이브에 내도 되나

**사용자 원칙 2026-11-03**(PM 전달): "QA의 목표는 대기업 서비스에 가깝게 만들어야하는거야", "개발도 마찬가지지로 대기업이지만 QA도 대기업으로해야해"

- QA는 "코드가 맞나"만 보지 않습니다. "대용량 대기업 서비스처럼 라이브에 내도 되나"를 봅니다. 그래서 코드·보안·명세 관문(RUST·ASYNC·DEPS·SPEC·ACC·DBDES·SEC·FINOPS·WEB·CONV·HOST)에 **서비스 준비도 관문**(PRR·PERF·REL·OPS·DEPLOY·TEST·ARCH·XC·PRIV)을 더했습니다.
- 판정 기준은 [`docs/architecture/principles.md`](../architecture/principles.md)를 QA에도 똑같이 씁니다. 관문마다 표준 출처를 적었습니다. 표준보다 낮은 기준을 QA가 임의로 받지 않습니다. 다르게 가려면 설계서에 이유·출처·PM 확인이 있어야 합니다.
- **하네스와 나누기**: 기계로 볼 수 있는 것은 하네스(MooKKoHarness) 검사 결과를 근거로 씁니다. QA는 사람의 판단이 필요한 부분을 봅니다. 관문마다 "자동 근거"와 "QA 판단"을 나눠 적었습니다. 아직 없는 검사는 "하네스에 요청"으로 표시했고, QA가 통합 담당에게 요청합니다.

### 새 관문의 적용 단계

| 단계 | 관문 | 기존 커밋 | 출시 관문(L4) |
|---|---|---|---|
| 1차(바로) | PRR-01, PERF-01, OPS-01, DEPLOY-01 | 경고(`warn`)로 판정 | `fail`로 셈 |
| 2차 | REL-01, TEST-01, ARCH-01, XC-01, PRIV-01, SEC-01·WEB-01 보강 | 경고(`warn`)로 판정 | `fail`로 셈 |
| 3차(보안 담당 2026-11-04) | SEC-02, SEC-03, SEC-04 | 경고(`warn`)로 판정 | `fail`로 셈 |

- 경고 단계에서도 판정은 관문마다 `pass | warn | na | waived`로 남깁니다. `warn`은 고칠 점이 있다는 뜻이고 통합을 막지 않습니다. 같은 지적은 출시 관문에서 `fail`이 됩니다.
- **출시 관문(L4)**은 서비스를 처음 라이브에 열 때와 **큰 변경** 때입니다(PM 대행 2026-11-03). 큰 변경은 아래입니다.
  - 새 서비스, 새 바깥 입구(공개 경로·API)
  - 하위 호환을 깨는 변경(API, DB 좁히기)
  - 인프라 구조 변경(클러스터·영역·DB 배치)
  - 돈·키·인증 기능
- 그 밖의 변경은 출시 관문을 거치지 않고 DEPLOY-01의 카나리 관문으로 갑니다.

## RUST-01 메모리 안전

- 모든 crate 루트(lib·bin·test·bench·example·build script)에 `#![forbid(unsafe_code)]`. CI가 `cargo metadata`의 모든 대상을 확인합니다.
- 워크스페이스 `[workspace.lints.rust] unsafe_code = "forbid"`를 각 crate가 `[lints] workspace = true`로 받습니다.
- `unsafe`를 안에 쓰는 외부 crate는 DEPS-01 근거(널리 쓰이고 감사된 것, 대안이 없음)가 있어야 합니다.

## RUST-02 오류 처리

- `unwrap`·`expect`·`panic!`·`todo!`·`unimplemented!`·`dbg!` 금지(clippy deny). 시험 코드의 `unwrap`·`expect`만 허용합니다.
- 라이브러리 오류는 형식 있는 오류(`thiserror` 등), 실행 파일 경계에서만 묶습니다. 오류에 비밀값·개인정보를 넣지 않습니다.
- 정수 넘침은 `checked_*`/`saturating_*`로 다룹니다(돈과 수량은 반드시 `checked_*`).

## ASYNC-01 비동기

- 요청 처리 경로에서 `std::thread::sleep`, 동기 파일·네트워크 I/O, `block_on`, 오래 잡는 동기 잠금을 쓰지 않습니다. 막는 일은 `spawn_blocking`으로 상한을 두고 넘깁니다.
- 외부 호출에는 기한(timeout)과 재시도 상한이 있습니다. 동시 실행에는 상한(세마포어)이 있고, 무거운 일은 남은 메모리를 보고 줄이거나 미룹니다.

## DEPS-01 의존성

- `cargo deny --locked check`(취약점·yanked·라이선스·출처·와일드카드)와 `cargo audit --deny warnings` 통과.
- 새 crate는 커밋 본문 또는 설계서에 필요·대안·유지 상태·`unsafe` 여부·라이선스를 적습니다. 출처는 crates.io만, git 의존성 금지.
- `Cargo.lock`은 커밋합니다. 빌드는 `--locked`입니다.

## SPEC-01 명세 근거

- `docs/spec/`의 모든 기능·API 계약·DB 스키마·돈 규칙·보안 규칙 항목에 근거가 있습니다: C# 판에서 가져온 것은 C# 사본의 상대 경로와 줄(예: `search/backend/src/Search.Api/Program.cs:42`), 새로 설계한 것은 "새 설계"와 이유.
- gRPC 계약은 `proto/mookko/<서비스>/v1/`에 Protobuf 규약대로 씁니다(C# `.proto`는 참고만). 바깥 HTTP 계약은 OpenAPI 3.1로 적습니다.
- 확정하지 못한 것은 `open-questions.md`에, 사용자 결정이 필요한 것은 그렇게 표시합니다. 추측을 사실처럼 적지 않습니다.

## ACC-01 인수 시험

- 외부 계약(HTTP 상태·본문·헤더, gRPC 응답·상태, DB에 남는 결과)만 검사하고 구현 언어를 모릅니다.
- 대상 주소·DB 연결은 JSON 설정 파일로 받습니다. 대상이 없으면 "건너뜀"을 분명히 출력하고 통과로 세지 않습니다.
- 인수 시험은 **Rust 판에서** 통과한 실행 기록(명령·대상 커밋·통과/실패 수)이 있어야 합니다. C# 판에서는 돌리지 않습니다(C# 판은 나중에 삭제, 사용자 결정 2026-10-29).

## DBDES-01 DB 설계

- 스키마를 바꾸는 커밋보다 앞서 설계서 `<crate>/docs/data-model.md`를 바꾼 커밋이 있고, QA 설계 분야(qa-design)가 그 설계를 `design:approved`로 판정했어야 합니다(맨 위 QA 상태의 재개 규칙).
- 이관은 앞으로만 가되 되돌리는 방법을 적습니다. 색인·제약·잠금 시간·데이터 양을 적습니다.
- 운영 결정 표의 표준 출처 칸(ARCH-01)과 열마다 데이터 등급(PRIV-01·SEC-01)을 함께 봅니다.

## SEC-01 보안

- **범위(2026-11-04 정리)**: SEC-01은 **앱·기능 보안**(인증·세션·인가·입력·암호·쿠키·비밀값 다루기, ASVS·STRIDE)입니다. 그 아래 플랫폼 층은 SEC-02(피해 범위·격리)·SEC-03(탐지·대응)·SEC-04(취약점·패치 지연)가 보고, 워크로드 기본 위생은 HOST-01이 봅니다. 기준 정본은 보안 전문 담당의 [`docs/architecture/security.md`](../architecture/security.md)와 규약 [`conventions/security.md`](conventions/security.md)(SC-*)입니다.
- **옛 번호 대응(2026-11-04, PM 지시)**: qa-engine 11-03 지적 번호 "SEC-2·SEC-3·SEC-4"는 새 관문 SEC-02~04와 헷갈려 **`QE-SEC-2`(운영 파일 KEK 금지, KMS 감싼 키만)·`QE-SEC-3`(직원 로그인 MFA 필수)·`QE-SEC-4`(직원 세션 12시간·유휴 15분)**으로 부릅니다. 셋 다 이 SEC-01 아래의 운영 설정 검사(`ci/check-production-config.py`)이고, 관문 SEC-02~04와는 상관없습니다. 옛 이름이 남은 곳(검사 머리말·오류 문구, 제품 `docs/coordination/engine-priority.md`)은 그 파일 담당이 고칩니다.
- 인증·인가(OpenIddict 대응), 소셜 로그인 5종, 토큰 수명·회전·폐기, 비밀값 보관(HSM/Pkcs11 대응), 감사 기록, 개인정보 최소화.
- C# 판에 있던 보안 수준보다 약해지면 안 됩니다(기능 파악용 참고). **약해지는 변경은 사용자 결정 없이는 `fail`입니다**(규칙 문서 `docs/policy/`를 약하게 바꾸는 것도 포함).
- 쿠키는 모두 `__Host-` 접두어(Secure, Path=/, `Domain` 없음). 상위 도메인(`Domain=mookko.com`) 쿠키는 금지입니다(사용자 콘텐츠 하위 도메인과 분리). 서버(엔진 BFF)와 화면 모두 해당합니다.
- **보강(2026-11-03, 2차)** — 표준 출처: OWASP ASVS 4.0.3(L2, 돈·키·인증은 L3), Microsoft STRIDE 위협 모델, OWASP SAMM.
  - 기능마다 **위협 모델**(STRIDE, 신뢰 경계·자산·위협·막는 장치)이 명세(`docs/spec/<서비스>/threat-model.md` 또는 명세 안 절)에 있어야 합니다.
  - 기능마다 **ASVS 수준**을 적고, 그 수준의 해당 장(인증 V2, 세션 V3, 접근 제어 V4, 입력 V5, 암호 V6, 오류·로그 V7, 데이터 보호 V8, 통신 V9)을 판정합니다. 돈·키·인증 기능은 L3입니다.
  - **자동 근거**: SAST(Semgrep 규칙 묶음), gitleaks·trivy(이미 check-all), DAST(내부 시험 서버의 OWASP ZAP 기준 검사) 결과. Semgrep·DAST는 **하네스에 요청**.
  - **QA 판단**: 위협 모델이 실제 경계와 맞는지, 막는 장치가 코드·시험에 있는지(파일:줄).

## SEC-02 피해 범위·격리 (3차)

표준 출처: CIS GKE Benchmark(노드 서비스 계정·Workload Identity·메타데이터 숨김·Shielded 노드·사설 클러스터·GKE Sandbox 항목), MITRE ATT&CK for Containers(T1611 Escape to Host, T1068, T1190), GKE 강화 안내서·GKE Sandbox 문서, Kubernetes ValidatingAdmissionPolicy.

- 노드 root를 얻어도 피해가 그 풀의 워크로드에 묶이게 합니다. 신뢰 등급별 노드 풀(`system`·`general`·`sandbox`·`control`·`keys`·`db-money`·`db-general`)이고, **키 DB·운영툴·Argo CD는 처음부터 전용 풀**입니다(security.md §2, SC-NODE-1).
- 전용 풀의 toleration·nodeSelector·nodeAffinity는 정해진 네임스페이스만 쓰고(SC-NODE-2), 노드 풀마다 전용 노드 서비스 계정·Workload Identity·Shielded·사설 노드(SC-NODE-3), Kubernetes SA 하나 = IAM 주체 하나(SC-NODE-4).
- 바깥 바이트 파서·바깥 주소 가져오기는 gVisor 샌드박스의 그 일만 하는 Deployment(SC-SBX-1~3). 공개 Node.js SSR은 부하 시험 뒤 보안 담당이 정하고, 정하기 전에는 L4 `fail`(SC-SBX-4).
- 특권은 `mookko-security` 네임스페이스의 등록 이미지만(SC-PRIV-1).
- **자동 근거**: `ci/check-containers.py` 확장 — 풀 toleration·nodeAffinity 대응표(`docs/policy/node-pools.json`), `mookko.io/input: untrusted` 라벨이면 `runtimeClassName: gvisor`·비밀값·SA 권한 없음, 특권은 `docs/policy/privileged-allowlist.json`만 → **하네스에 요청**. 노드 풀 설정은 OpenTofu plan 정책 검사(IaC 저장소가 생기면) → **하네스에 요청**.
- **QA 판단**: 라벨을 달아야 할 Deployment에 빠지지 않았는지(실제 바깥 입력 경로와 대조), Workload Identity 권한이 실제 호출과 맞는지, 풀 배치가 security.md 표와 맞는지.
- HOST-01과 나누기: 워크로드 하나하나의 위생(PSS restricted·NetworkPolicy·자원·서명)은 HOST-01, 워크로드끼리 같은 노드에 둘지(피해 범위)는 SEC-02입니다.

## SEC-03 탐지·대응 (3차)

표준 출처: NIST SP 800-61 Rev. 3(CSF 2.0 기반 사고 대응), Google "Incident Management Guide"(IMAG)·SRE 책 14·15장, CNCF Falco, Cilium Tetragon, MITRE ATT&CK for Containers, ISMS-P 2.11(사고 예방 및 대응).

- **런타임 감지는 출시 전 필수**입니다: Falco는 모든 노드 풀, Tetragon은 `keys`·`control`(host-security §7.1, SC-DET-1). 규칙마다 ATT&CK 번호·등급·runbook, 끄기는 보안 담당 확인 + 두 사람 승인(SC-DET-2), 에이전트 끊김은 경보(SC-DET-3), 감사 로그는 보안 등급·WORM(SC-DET-4).
- **사고 대응 절차서**(`docs/architecture/incident-response.md`)가 하나만 있고(SC-IR-1), 출시 전 탁상 훈련 1회 + 노드 격리·버리기·비밀값 교체 기술 훈련 1회 기록(SC-IR-2), 새 비밀값·키·인증서는 교체 방법을 함께 적음(SC-IR-3).
- **자동 근거**: 감지 매니페스트가 모든 풀을 덮는지, 규칙 파일의 칸(기법·등급·runbook), `check-prr.py` 확장(훈련 기록 칸) → **하네스에 요청**.
- **QA 판단**: 가짜 공격 시험(예: falco event-generator)에서 경보가 사람에게 닿았는지, 훈련에 걸린 시간이 incident-response §5.1 목표 안인지, 교체 표가 실제 비밀값 목록과 맞는지.
- PRR-01과 나누기: 당번·호출·사후 검토 틀은 PRR-01과 같은 문서(incident-response)를 봅니다. 보안 사고(`SEV<n>-SEC`)의 조사·증거·신고·런타임 감지는 SEC-03입니다.

## SEC-04 취약점·패치 지연 (3차)

표준 출처: CISA BOD 22-01(KEV 기한), NIST SP 800-40 Rev. 4(엔터프라이즈 패치 관리), ISMS-P 2.10.8(패치관리), CIS GKE Benchmark(노드 자동 업그레이드·릴리스 채널).

- 패치 기한(host-security §1: KEV·실제 공격 48시간, 치명 7일)은 HOST-01이 봅니다. SEC-04는 **기한을 벤더 때문에 못 맞출 때**입니다(계기: CVE-2026-98432, Ubuntu 고친 판 늦음).
- 기한의 절반이 지나기 전에 제품 `docs/policy/vuln-register.json` 항목(SC-VULN-1), 완화 순서는 host-security §1.1(기록 → 노출 끊기 → 격리 → 감지 → 다른 이미지 → 30일 넘으면 사용자 결정, SC-VULN-2), 고친 판이 나오면 기한을 다시 세고 닫음(SC-VULN-3), 기반·제3자 이미지도 같음(SC-VULN-4).
- **자동 근거**: 기록부 형식·기한 검사(`expires` 최대 30일, 지나면 실패, waivers와 같은 방식), 이미지 출처가 우리 레지스트리인지(`check-containers.py`) → **하네스에 요청**.
- **QA 판단**: 노출 경로 판단이 맞는지(실제 망 구성과 대조), 완화가 기다리기만이 아닌지.

## 보안 설계 검토 (SEC-01~04 공통)

- 새 바깥 입구·바깥 주소 가져오기, 돈·키·인증·MFA·세션·비밀값·서명, 풀·네임스페이스·RBAC·Workload Identity·NetworkPolicy 넓히기, 특권·샌드박스 예외·감지 규칙 끄기는 설계서·명세에 보안 담당의 `security:reviewed <날짜> <세션>` 줄이 있어야 출시 관문(L4)을 넘습니다(SC-REV-1). 개발·통합은 막지 않습니다. 보안 담당은 한 영업일 안에 검토합니다(SC-REV-2).
- 판정 분야는 QAManager가 정합니다. 보안 담당 제안: 매니페스트·IaC·기록부 검사 대조는 mookko-rust-qa(HOST-01과 함께), 대응 절차·훈련 기록은 qa-services(PRR-01과 함께).

## FINOPS-01 돈

- 금액은 정수 최소 단위와 통화 코드. 부동소수점 금지. 반올림 규칙 명시.
- 복식부기 원장, 멱등 키, 대사(외부 PG·은행과), 마감, 이중 승인, 감사 기록.
- 돈이 오가는 서비스(결제·월렛·정산)는 4단계의 마지막에 만듭니다.

## WEB-01 웹 화면

- 스택: React + TypeScript + Tailwind CSS, `web/` pnpm 모노레포(사용자 결정 2026-10-29). 내부·로그인 뒤 화면은 Vite SPA, SEO가 필요한 공개 화면만 Next.js SSR.
- `pnpm install --frozen-lockfile`(lock 고정), `pnpm audit`(알려진 취약점 없음), 라이선스 허용 목록(DEPS-01과 같은 목록), 레지스트리는 npm 공식만, git·URL 의존성 금지.
- `tsc --noEmit`(strict), eslint, `vite build`/`next build` 통과.
- 새 패키지는 필요·대안·유지 상태·라이선스를 커밋 본문이나 설계서에 적습니다. 의존성은 최소로 둡니다.
- 화면 코드에 비밀값·토큰을 넣지 않습니다. API 주소는 코드에 두지 않고 배포 설정(JSON)에서 읽거나 같은 출처(same-origin)를 씁니다.
- API 클라이언트는 `.proto`에서 생성한 것만 씁니다(손으로 쓴 요청 형식 금지).
- **보강(2026-11-03, 2차)** — 표준 출처: W3C WCAG 2.2, Google Core Web Vitals(web.dev).
  - **접근성**: WCAG 2.2 AA. 자동 근거는 axe-core 검사(화면 시험 안), QA 판단은 키보드만으로 쓰기·초점 순서·대비·화면 읽기 프로그램 이름.
  - **성능 예산**: 공개 화면은 75번째 백분위 기준 LCP 2.5초 이하, INP 200ms 이하, CLS 0.1 이하. 자동 근거는 Lighthouse CI 예산 파일, 라이브는 RUM 지표. Lighthouse CI·axe는 **하네스에 요청**.

## CONV-01 언어별 코딩 규약

- 정본: `docs/policy/conventions/`(Rust `rust.md`, 프론트엔드 `frontend.md`, SQL `sql.md`, Protobuf `proto.md`, 도구 `tools.md`). 목표 순서 안정성 → 속도 → 모듈화 → 재사용.
- 바뀐 파일의 언어 규약을 규칙 번호로 판정합니다. **[lint]·[deny]·[검사]** 규칙은 하네스가 돌린 실행 결과로, **[QA]** 규칙은 파일·줄 근거로 `pass`를 적습니다.
- 규칙 끄기(`#[allow]`·`#[expect]`·`eslint-disable`·`@ts-ignore` 등)는 `docs/policy/lint-exceptions.json`에 이유·만료일로 등록된 것만 허용합니다(하네스 `ci/check-lint-escapes.py`).
- 개발·시험 컨테이너 포트는 루프백에만 엽니다(`-p`는 127.0.0.1·[::1]·"$BIND_HOST", `-P`·`--network host` 금지, 하네스 `config/dev/*.json`의 bindHost는 루프백, 하네스 `ci/check-dev-exposure.py`). WSL이 mirrored라 모든 주소에 열면 PC 밖에서 보입니다.
- 시험 임시 폴더는 `$TMPDIR/mookko-test/...` 아래에만 만들고, 지울 때는 그 실행이 만든 폴더만, 실패한 시험의 폴더는 남깁니다(하네스 `ci/check-test-tempdirs.py`, tools.md T-SH-3).
- 규약을 약하게 바꾸는 변경(lint 끄기, 상한 올리기, 금지 목록 줄이기)은 사용자 결정 없이는 `fail`입니다.

## HOST-01 운영 실행 환경

- **사용자 결정 2026-11-03**: 운영은 Docker 이미지 + Kubernetes(라이브 GKE Standard, 노드 Container-Optimized OS), 배포는 GitOps(Argo CD·Argo Rollouts), 앞단은 Envoy Gateway(Gateway API)입니다. 앱 서버를 VM에 바로 올리고 systemd로 돌리는 전제는 없앴습니다.
- **운영 기준**: [`docs/architecture/deploy-containers.md`](../architecture/deploy-containers.md) §3(보안 기준)·§4(패치·배포)
  - Pod Security `restricted`, 읽기 전용 루트, 호스트 공유 금지, NetworkPolicy 기본 차단, 자원 requests·limits
  - 멀티 AZ 분산(`topologySpreadConstraints` maxSkew 1, 최소 3), PDB, HPA
  - 상태 확인 probe, 비밀값은 KMS·읽기 전용 파일, admission에서 이미지 서명 확인, 다이제스트 고정
  - GitOps: 승인된 판만 설정 저장소에 커밋, 되돌리기는 이전 판 커밋, 비상 경로(break-glass)
- **노드·패치 기준**: [`docs/architecture/host-security.md`](../architecture/host-security.md) §0(COS에서 지키는 법)·§1(패치 기한: KEV·실제 공격 48시간, 치명 7일)·§5(앞단 방어)·§6(공급망)·§7(침입 감지)
- **내부 시험 서버는 따로 봅니다**: Ubuntu 24.04 LTS 기준(host-security §0·§2~§4, H-1·H-9, `docs/coordination/internal-test-server-plan.md`)입니다. 시험 클러스터에도 deploy-containers §3·§4를 그대로 겁니다(§11). 운영과 다른 점(노드 수·영역 수·디스크·CDN 없음)은 시험 결과에 적습니다.
- **자동 근거**: 하네스 `ci/check-containers.py`(Dockerfile·매니페스트·Compose, check-all). 내부 시험 서버의 `*.service`가 저장소에 있으면 하네스 `ci/check-systemd-units.py`도 그대로 봅니다. 예외는 `waivers.json`에 `rule`이 HOST-01인 기한 있는 항목만 받습니다.
- **SEC-02·SEC-04와 나누기**(2026-11-04): 노드 풀 나누기·샌드박스·특권 예외는 SEC-02, 벤더 패치가 늦을 때의 완화·기록부는 SEC-04입니다. 패치 기한 자체와 워크로드 위생은 그대로 HOST-01입니다.
- **QA 판단**: 매니페스트가 서비스의 실제 의존(DB·캐시·다른 서비스)과 맞는 NetworkPolicy를 갖는지, probe가 진짜 준비 상태를 보는지, 비상 경로가 문서와 훈련 기록으로 있는지.
- 기준을 약하게 바꾸는 변경(보안 설정 빼기, 분산·최소 수 줄이기, 기한 늘리기, 서명 확인 끄기)은 사용자 결정 없이는 `fail`입니다.

## PRR-01 출시 준비 검토 (1차)

표준 출처: Google SRE 책 "The Evolving SRE Engagement Model"(32장, PRR)·"Reliable Product Launches at Scale"(27장)·부록 E "Launch Coordination Checklist", SRE 워크북 "SRE Engagement Model"(18장)·"Alerting on SLOs"(5장), AWS Well-Architected 운영 우수성·안정성 기둥. 장 번호는 sre.google 목차에서 확인했습니다(2026-11-03).

서비스를 처음 열기 전과 큰 변경 때 봅니다. 서비스마다 `docs/spec/<서비스>/prr.md` 한 장에 아래를 채우고, QA가 항목마다 판정합니다.

| 항목 | 있어야 하는 것 |
|---|---|
| SLO·SLI | 사용자에게 보이는 SLI(가용성·지연·정확성)와 SLO 값, 측정 지점, 오류 예산 정책 |
| 경보 | 다중 창 소진율(burn rate) 경보(SRE 워크북 5장). 원인 경보보다 증상 경보 |
| runbook | 경보마다 runbook 링크(확인할 것·조치·되돌리기·올릴 곳) |
| 당번 | 호출 대상·순번·올리는 단계, 사후 검토(postmortem) 양식. 등급·역할·사후 검토 틀은 `docs/architecture/incident-response.md` 하나를 씀(서비스가 따로 만들지 않음, SEC-03과 같은 문서) |
| 용량 | 예상 부하와 여유분, 근거는 PERF-01 부하 시험 결과 |
| 의존 장애 | 의존 서비스·DB·캐시가 죽거나 느릴 때의 동작(REL-01 결과) |
| 되돌리기 | 되돌리기 시험 기록(DEPLOY-01) |
| 비상 경로 | 운영툴 없이 되돌리는 경로와 훈련 기록(deploy-containers §4) |
| 백업·복구 | 백업 대상·RPO·RTO와 복구 훈련 기록(deploy-containers §12, database.md §6) |

- **자동 근거**: `prr.md`의 칸이 비었는지, 경보 규칙마다 runbook 링크가 있는지 → **하네스에 요청**.
- **QA 판단**: SLO가 사용자 경험을 대표하는지, 경보가 SLO와 이어지는지, runbook이 실제로 따라 할 수 있는지.

## PERF-01 성능 (1차)

표준 출처: SRE 워크북 "Managing Load"(11장)·"Identifying and Recovering from Overload"(17장), SRE 책 "Handling Overload"(21장), AWS Well-Architected 성능 효율 기둥, AWS Builders' Library "Using load shedding to avoid overload".

- 명세(`docs/spec/<서비스>/`)에 목표(p95·p99 지연, 처리량, 동시 연결)가 있어야 합니다. 없으면 SPEC-01 고칠 점으로 함께 올립니다.
- 목표는 **부하 시험 결과**로 판정합니다. 부하 시험은 내부 서버의 같은 구성 시험 클러스터에서 돌립니다(deploy-containers §11). 결과에 대상 커밋·이미지 다이제스트·환경 차이를 적습니다.
- **판마다 벤치 회귀**를 봅니다(PM 대행 2026-11-03).
  - 기준은 정해 둔 기준 판 대비 p99·처리량입니다. 서비스가 명세에 자기 목표를 정하면 그 값을 쓰고, 정하지 않았으면 5%입니다.
  - 잡음으로 잘못 판정하지 않도록, 같은 장비에서 판마다 여러 번(기본 5번) 돌려 중앙값과 분산을 비교합니다.
  - 차이가 기준을 넘고 **잡음 범위도 넘을 때만** `fail`입니다. 기준은 넘었지만 잡음 범위 안이면 `warn`입니다.
  - 기준 장비는 내부 시험 서버입니다. 그 전까지는 WSL(MooKKo-Linux)이고, 결과에 장비를 적습니다. 장비가 다른 결과끼리는 비교하지 않습니다.
  - 부하 시험과 벤치는 빌드 자리 안에서만 돌리고 메모리 관문(Windows 전체 사용률 85%·90%)을 지킵니다.
- **자동 근거**: 벤치 회귀 비교(criterion 등 결과를 기준 판과 대조) → **하네스에 요청**. 부하 시험 실행 기록 형식 → **하네스에 요청**.
- **QA 판단**: 부하 모양이 실제 트래픽(읽기·쓰기 비율, 큰 사용자, 몰림)을 닮았는지, 병목 설명이 맞는지.

## REL-01 장애 견딤 (2차)

표준 출처: Netflix Chaos Engineering 원칙(principlesofchaos.org)·Chaos Monkey, AWS Builders' Library "Timeouts, retries and backoff with jitter"·"Avoiding insurmountable queue backlogs", Google SRE 책 21장(과부하)·22장(연쇄 장애).

- 장애 주입을 견디는지 시험 기록으로 봅니다: 의존 서비스 죽음·느려짐, DB 주 서버 바뀜, 캐시 없음, Pod 죽음, 영역(AZ) 하나 잃음.
- 코드와 시험으로 확인할 것: 모든 바깥 호출의 기한, 재시도 예산(지터 있는 지수 백오프, 전체 재시도 비율 상한), 부하 버리기(우선순위), 회로 차단, 대기열 상한.
- **자동 근거**: 기한 없는 바깥 호출 찾기(ASYNC-01 검사 확장), 장애 주입 시험 실행 기록 → **하네스에 요청**.
- **QA 판단**: 장애 때 사용자에게 보이는 결과가 명세와 맞는지, 재시도가 연쇄 장애를 키우지 않는지.

## OPS-01 운영 가능성 (1차)

표준 출처: 사용자 결정 2026-11-03("전부다 운영툴에서 셋팅할수있어야해"), Facebook Configerator(설정 관리), SRE 워크북 "Configuration Design and Best Practices"(14장)·"Configuration Specifics"(15장).

- 설정 목록([`docs/architecture/config-catalog.md`](../architecture/config-catalog.md)) 밖의 숫자·경로·주소가 코드에 없습니다.
- 설정은 운영툴 화면에서 바꿀 수 있고, 바꿀 때마다 MFA·사유·감사가 남습니다(deploy-containers §7′).
- 기능마다 킬 스위치(끄는 설정)가 있습니다. 위험한 새 기능은 기본 꺼짐입니다.
- 지표·로그·추적이 나옵니다(`docs/spec/observability/README.md`). 경보에 쓸 지표 이름은 코드와 문서가 같습니다.
- 서버를 다시 켜지 않고 설정을 다시 읽습니다(서버별, 읽은 판을 지표로 냄).
- **자동 근거**: 하네스 `ci/check-hardcoded-values.py`(`docs/policy/hardcoded-values.json` 기준), 하네스 `ci/check-no-hardcoded-endpoints.py`. 설정 목록과 코드의 설정 키 대조, 지표 이름 대조 → **하네스에 요청**.
- **QA 판단**: 설정 이름·범위·기본값이 운영자가 쓸 수 있는 모양인지, 킬 스위치가 실제로 그 기능을 끄는지.

## DEPLOY-01 배포 안전 (1차)

표준 출처: AWS Builders' Library "Automating safe, hands-off deployments", SRE 워크북 "Canarying Releases"(16장), Argo Rollouts(분석 기반 카나리), Facebook "Holistic Configuration Management"(설정도 단계 배포), SLSA(같은 산출물 승격).

- **신·구 판이 함께 돌아도 맞아야 합니다.**
  - API: proto 하위 호환(필드 번호 재사용·형 변경·필수화 금지, `proto.md` 규칙)
  - DB: 넓히기 → 옮기기 → 좁히기(`sql.md`), 옛 판이 새 스키마에서도 돌고 새 판이 옛 스키마에서도 도는지
- 카나리와 자동 되돌림이 시험으로 확인돼 있습니다(Argo Rollouts 분석 실패 → 자동 중단).
- 설정 변경도 코드처럼 단계 배포합니다(카나리 → 넓히기, 되돌리기 가능).
- 시험을 통과한 **같은 이미지 다이제스트**를 다음 단계로 올립니다. 단계마다 다시 빌드하지 않습니다.
- **자동 근거**: proto 호환 검사(`buf breaking` 등), 이관 넓히기·좁히기 검사(check-db 확장), 매니페스트의 다이제스트 고정(check-containers) → proto 호환 검사는 **하네스에 요청**.
- **QA 판단**: 카나리 분석 지표가 그 변경의 위험을 잡는지, 되돌리기 시험이 실제 경로를 탔는지.

## TEST-01 시험 품질 (2차)

표준 출처: Google Testing Blog "Flaky Tests at Google and How We Mitigate Them", Google "Software Engineering at Google" 11~14장, OSS-Fuzz.

- 실제 시간·`sleep`에 기대는 시험을 쓰지 않습니다(엔진 `FixedClock` 등 시계 포트를 씁니다).
- 파서·바깥 입력 처리(요청 본문, 파일·이미지, 패킷, 설정)에 퍼징 대상이 있습니다(cargo-fuzz).
- 규칙이 많은 계산(돈·권한·시각 경계)에 속성 시험(proptest 등)이 있습니다.
- 흔들리는 시험은 격리 목록에 기한과 함께 등록하고, 기한 안에 고치거나 지웁니다.
- 시험 실효성 지표(변이 시험 cargo-mutants 생존 비율 또는 분기 커버리지)에 목표를 둡니다. 목표 값은 서비스별 명세에 적습니다.
- **자동 근거**: 시험 안 `sleep`·실제 시각 찾기, 퍼징 대상 목록 대조, 흔들리는 시험 등록부 기한 검사, 변이 시험 결과 → **하네스에 요청**.
- **QA 판단**: 시험이 명세의 경계·실패 경로를 덮는지, 표본만 맞추는 시험이 아닌지.

## ARCH-01 표준 준수 (2차)

표준 출처: [`docs/architecture/principles.md`](../architecture/principles.md).

- 운영·인프라 결정 표에 "표준 출처" 칸이 있고 채워져 있습니다. 표준과 다르면 이유·출처·PM 확인 날짜가 있습니다.
- 공용 기능(인증·MFA·시계·이름 검사·감사 원장·저장소 틀·권한·멱등 영수증 등)은 엔진에만 있고, 서비스는 엔진 것을 씁니다.
- **자동 근거**: 하네스 `ci/check-design-sources.py`(`docs/policy/design-sources.json`), 하네스 `ci/check-engine-reuse.py`.
- **QA 판단**: 적힌 출처가 실제로 그 결정을 뒷받침하는지(출처만 붙인 것이 아닌지).

## XC-01 서비스 사이 일관성 (2차)

근거: 사용자 결정 2026-11-03(PM 전달). 지적 번호는 `XC-`로 시작합니다.

- 같은 개념(인증·최근 MFA·시계·시각·이름 검사·감사 원장·저장소 틀·권한 검사·읽기 경로)을 서비스마다 같은 규칙으로 하는지 **주 1회** 판정합니다. 새 서비스를 붙일 때도 봅니다.
- 개념마다 맡는 QA 세션을 하나로 정하고, 그 세션이 엔진과 모든 서비스를 끝까지 봅니다(시계·저장소 틀·권한은 qa-engine, MFA·이름·감사 원장은 qa-services, SQL 부분은 qa-design).
- **자동 근거**: `check-engine-reuse.py`, 같은 개념 재구현 모양 검사(mookko-rust-qa가 모은 lint 후보).
- **QA 판단**: 동작 차이(유효 시간·허용 글자·사슬 방식·트랜잭션 종류)가 사용자나 감사 결과를 어긋나게 하는지.

## PRIV-01 개인정보·법무 (2차)

표준 출처:
- 개인정보 보호법(법률 제19234호, 2023-03-14 개정): 제28조의8(개인정보의 국외 이전), 제16조(개인정보의 수집 제한), 제21조(개인정보의 파기). 조문 제목은 한국법제연구원 영문 법령(elaw.klri.re.kr)에서 확인했습니다(2026-11-03). 원문은 법무 확인 때 국가법령정보센터에서 다시 봅니다.
- 불법촬영물 유통 방지: 전기통신사업법 제22조의5(부가통신사업자의 불법촬영물등 유통방지 조치)와 정보통신망법 제44조의9(유통방지 책임자). 대상 규모 기준은 시행령에 있습니다.
- 개인정보보호위원회 안내서.

- 법이 걸리는 기능을 판정합니다: 국외 이전(백업·대기 DB·외부 서비스), 보관 기한과 파기, 최소 수집, 동의·고지, 불법촬영물 걸러내기(사진·영상 올리기).
- 열마다 데이터 등급과 보관 기한이 설계서에 있습니다(sql.md).
- 사용자 법무 확인이 필요한 것은 "법무 확인 필요"로 표시하고, 확인 전에는 보수적인 안(국내 보관, 짧은 보관, 기본 꺼짐)으로 갑니다.
- **자동 근거**: 데이터 등급 칸 누락(check-db), 보관 기한 칸 누락 → 보관 기한 검사는 **하네스에 요청**.
- **QA 판단**: 실제 데이터 흐름(로그·지표·백업 포함)이 등급·기한과 맞는지.

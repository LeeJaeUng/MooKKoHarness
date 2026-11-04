# MooKKoHarness 설계

처음 정한 날: 2026-10-29(하네스를 Rust로 새로 만듦). 고친 날: 2026-11-03, 2026-11-04.
- 이름을 MooKKoRustDev에서 MooKKoHarness로 바꿈(사용자 "MooKKoRustDev 이름을 하네스로 바꿔야하는거 아니야? 영어로").
- 제품에 흩어져 있던 검사·관문·규약을 여기로 모음(사용자 "하네스 한쪽에 몰아줘").
- 개발은 AI 매니저를 거치지 않고 Claude 앱 세션(PM → 하네스 담당 → 하위 세션)에서 함, 하네스는 허브에 등록하지 않음
  (사용자 2026-11-03 "ai매니져 안쓰고 여기서 할꺼야", "허브에도 등록안할꺼고"). 그래서 서버 H3·H4는 멈춤(아래 단계).

관리 대상은 제품 저장소 MooKKo(로컬 폴더 `MooKKoRust`, 원격 `LeeJaeUng/MooKKo`)입니다. 저장소 경로는 설정 JSON에서 읽습니다.

## 하네스의 역할

**하네스는 개발될 서비스들을 강하게 잡습니다.** 워커(AI)에게는 정해진 방식대로만 개발하도록 규칙을 줍니다. 어긋난 커밋은 검사·관문에서 막아 `foundation/engine`·`main`에 들어가지 못하게 합니다. 하네스 자신은 화면이 없습니다(API와 실시간 알림만).

일의 흐름은 이렇습니다. 워커는 Claude 앱 세션입니다(PM이 지시 → 하네스 담당이 일감을 나눔 → 하위 세션이 개발·QA).
1. 담당 세션이 자기 worktree에서 커밋합니다.
2. Linux check-all을 돌립니다. 하네스 `ci/check-all.sh`가 제품 `harness.lock` 판으로 돕니다.
3. 분야별 QA 세션이 판정합니다.
4. 하네스 담당(통합)이 `integrate/*`에 모은 뒤 check-all을 다시 돌립니다.
5. `foundation/engine` fast-forward를 합니다.
6. 같은 커밋을 `main`에 push합니다.

하나라도 실패하면 들어가지 않습니다. 담당이 "통과했다"고 보고해도, 통합 판에서 다시 돌린 결과만 믿습니다.

## 제품과 나누는 법 (판 고정)

| 하네스 (이 저장소, 정본) | 제품 (MooKKo) |
|---|---|
| `ci/` 검사 본체와 그 표본, `dev/` 개발 도구(빌드 자리·메모리·디스크 관문·시험 DB), `config/dev/` 그 설정 | 얇은 진입점 `scripts/ci/check-all.sh`·`scripts/dev/*.sh` → `scripts/harness.sh` |
| `policy/gates.md`·`gates.json`, `policy/conventions/`, `skills/`, `rules/` | 고정 판의 사본(`docs/policy/gates.*`·`docs/policy/conventions/`·`.claude/skills/`, 워커가 읽는 자리) |
| 검사가 어떻게 판정하는지 | 이 제품만의 목록: 예외(`waivers`·`lint-exceptions`·`docs/policy/db/`), 래칫 기준(`hardcoded-values`·`test-time`), 설계 출처·PRR·식별자 등록부, 보안 등록부(`node-pools`·`privileged-allowlist`·`image-registries`·`vuln-register`, 보안 담당), `gitleaks.toml` |
| | `harness.lock`(하네스 커밋 40자), acceptance/, docs/spec·architecture·coordination, config/ |

- `scripts/harness.sh`는 하네스 저장소에서 고정 커밋을 `git archive`로 꺼내 `data/harness/<커밋>/`(다시 만들 수 있는 캐시)에 둡니다. 그다음 `MOOKKO_PRODUCT_ROOT`·`MOOKKO_HARNESS_DIR`·`MOOKKO_HARNESS_COMMIT`을 넘겨 실행합니다. 하네스 작업 사본에서 고치는 중인 파일은 쓰지 않으므로, 같은 제품 커밋은 늘 같은 검사를 받습니다.
- 판을 올리는 커밋은 통합 담당만 합니다. 판을 내리거나 검사를 약하게 바꾸는 것은 사용자 결정 없이는 실패입니다.
- 제품 사본이 고정 판과 다르면 `ci/check-harness-copies.py`가 알립니다(처음에는 경고).

## 강제하는 것

모든 항목은 두 곳에서 막습니다. (1) 워커가 받는 규칙(`rules/`·`skills/`·`policy/conventions/`), (2) check-all.

| 결정 (사용자) | 강제 방법 | 검사 |
|---|---|---|
| 모든 앱은 공용 서버 엔진 하나를 씀, 공용 기능은 엔진만 | 서비스 crate는 엔진 crate만 의존. 공용 기능 재구현 금지 | `check-boundaries.py`, `check-stack.py`, `check-engine-reuse.py` |
| 전부 모듈화(포트·어댑터) | 새 바깥 시스템은 엔진 포트 + 어댑터 crate + 적합성 시험으로만 | `check-boundaries.py`, QA 관문 |
| 포트·주소·경로·숫자는 설정 목록에서만 | 코드·상수에 두지 않음, 늘리면 래칫 실패 | `check-no-hardcoded-endpoints.py`, `check-hardcoded-values.py` |
| 웹 화면은 React + TypeScript + Tailwind (`web/` pnpm) | 다른 프레임워크·lock 금지, Next.js는 공개 SEO 화면만 | `check-stack.py`, WEB-01 |
| 라이브는 Docker + Kubernetes(GKE Standard, COS 노드, 서울 3영역), GitOps(Argo CD·Rollouts), 앞단 Envoy Gateway | 매니페스트 규칙·컨테이너 보안·짝 HPA/PDB·멀티 AZ | `check-containers.py`(노드 풀·샌드박스·특권·레지스트리 포함), `check-production-config.py`, `check-prr.py`(훈련 기록 포함), `check-vuln-register.py` |
| 시험은 내부 서버(생기기 전까지 WSL `MooKKo-Linux`), 빌드·시험은 Linux | Linux 밖 결과는 통과 아님. MooKKoRust 몫(WSL 6GB·빌드 자리 1개), PC 전체는 비상 관문(95%면 92%까지 기다리고 30분 넘으면 진행, PM 11-04) | `dev/build-slots.sh`, `dev/memory-guard.py` |
| 이름에 Rust를 붙이지 않음 | crate·실행 파일·이미지·설정 id에 `rust` 금지 | `check-stack.py` |
| 언어별 코딩 규약 | 정본 `policy/conventions/`와 `skills/`. lint 끄기는 예외 등록부(만료일)에 없으면 실패 | clippy·eslint·tsc, `check-lint-escapes.py`, QA CONV-01 |
| 메모리 안전·오류 처리 | `#![forbid(unsafe_code)]`, unwrap·expect·panic 금지, clippy -D warnings | `check-forbid-unsafe.py`, clippy |
| 의존성·보안 도구 | cargo-deny·cargo-audit, gitleaks·Trivy·OSV(판 고정·체크섬) | `check-security-tools.sh` |
| 설계 근거 | 결정마다 표준 출처, DB 스키마 변경은 qa-design `design:approved`(DBDES-01) 뒤 통합 | `check-design-sources.py`, QA |
| QA | 분야별 QA 세션(qa-design·qa-engine·qa-services·rust-qa). 당분간 개발·QA 모두 Claude(사용자 2026-10-29), 결과마다 엔진 표기 | 제품 `docs/policy/gates.md` |
| 돈은 마지막 | 엔진의 원장·멱등·메시지 기능이 시험으로 검증되기 전에 돈 서비스를 만들지 않음 | PM 규칙 |

규칙을 바꿀 때는 이렇게 합니다.
1. 이 저장소의 `ci/`·`policy/`·`skills/`·`rules/`를 고치고 커밋합니다.
2. 제품 `harness.lock`을 그 커밋으로 올립니다.
3. 제품 사본을 맞춥니다.
4. 제품 check-all을 통과시킵니다.

## 폴더

```
README.md         이 저장소 안내
docs/             design.md(이 문서), reference/(옛 판 기록. 경로·명령은 쓰지 않음)
policy/           관문(gates.md·gates.json), 언어별 규약(conventions/)
rules/            워커에게 주는 담당 규칙          skills/  언어별 AI 스킬
ci/               check-all.sh와 검사 본체, 검사 표본(fixtures/), DB 검사(db/)
dev/              개발 도구: 빌드 자리·메모리·디스크 관문·시험 DB·WSL 실행
config/           dev.example.json(하네스 서버), dev/(개발 도구 설정), roles.json(담당 구성: 담당표 owners.json과 맞춤)
apps/ crates/     하네스 서버(Rust, H1 뼈대에서 멈춤): mookko-dev 실행 파일, dev-config·dev-hub·dev-server
data/             실행 데이터(git 제외)
```

폴더마다 README에 "여기 두는 것 / 두지 않는 것"을 적습니다. `ci/check-folder-layout.py`가 하네스 저장소의 자리를 검사합니다(처음에는 경고).

하네스 서버(Rust, axum·tokio, H1 뼈대)는 **멈춰 둡니다**(2026-11-04). 서버가 하려던 담당·일감·워커 턴(H3·H4)은 Claude 앱
세션이 맡고, 허브·AI 매니저에 붙이지 않습니다. 코드는 그대로 두되 새로 키우지 않고 띄우지 않습니다. 다시 쓸지(예: GitHub에서 도는
반영 관문 H5) 지울지는 PM이 정합니다. 모든 crate 루트는 `#![forbid(unsafe_code)]`이고, 제품과 같은 lint를 씁니다.

## 운영 교훈 (세션 운영에 그대로 씀)

예전 C# 실행부의 기록에서 가져왔습니다(`docs/reference/`. 그 문서의 경로·명령은 쓰지 않습니다).
- 일감이 있을 때만 하위 세션에 주고, 담당 하나는 한 번에 일감 하나만 맡습니다. 무거운 단계(빌드·시험)는 빌드 자리 2개와
  메모리 관문(Windows 전체 85%/90%, MooKKo 작업만)을 거칩니다.
- 일감을 끝냈다고 세는 것은 담당의 보고와 커밋 해시뿐입니다. 세션 턴이 끝난 것을 QA 통과나 반영으로 세지 않습니다.
- 경계 판정은 그 담당이 만든 커밋만 봅니다(owners.json, 병합 커밋 규칙 포함).
- QA fail은 끝난 QA로 기록하고 개발 담당에게 되돌립니다.
- 담당 사이 파일 전달은 커밋 SHA와 저장소 안 경로로만 합니다.

## 단계

| 단계 | 상태 |
|---|---|
| H1 뼈대 | 설정·포트, `/health`, SSE (있음, 멈춤) |
| H2 강제 검사 | check-all과 검사 전부, 판 고정(`harness.lock`) (있음, 계속 늘림: `docs/coordination/harness-backlog.md`) |
| H3 담당·일감 | Claude 앱 세션으로 대신함(PM → 하네스 담당 → 하위 세션, 담당표 owners.json·roles.json) |
| H4 워커 한 턴 | Claude 앱 세션으로 대신함(세션마다 자기 worktree, 규칙은 `rules/`·`skills/`·제품 사본, 경계는 owners.json) |
| H5 QA·반영 | 지금은 하네스 담당이 함(분야별 QA 판정 → 판 고정 check-all → `foundation/engine`·`main` fast-forward·push). 배포 관문(이미지 서명·SLSA·Binary Authorization, 이관 묶기 S-MIG-14)은 H5에 들어감 |

## 정해야 할 것

1. **검사 실행 위치.** 내부 시험 서버(Linux)로 옮깁니다. 서버가 생기기 전까지는 WSL `MooKKo-Linux`입니다. 내부 서버 사양·OS·계정은 사용자 결정 대기입니다.
2. **H5 배포 관문을 어디서 돌릴지.** GitHub Actions(비공개 저장소)나 내부 서버. 라이브 배포를 시작하기 전에 정합니다.
3. **GitHub.**
   - `LeeJaeUng/MooKKoHarness` 저장소는 사용자가 만들고, PM이 처음 push합니다.
   - `LeeJaeUng/MooKKo` 기본 브랜치를 `main`으로 바꾸는 것은 사용자가 합니다.

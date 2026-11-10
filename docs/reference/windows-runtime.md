# Windows C# 실행 구조

> MooKKoDev 주(2026-10-29): 이 문서는 MooKKoDev에서 복사한 C# 실행부 설명입니다. 실행부 구조(AppContainer 격리, 원장, QA 영수증, 반영)는 같고, 다른 점은 README.md의 "MooKKoDev와 다른 점"에 적었습니다. 아래의 날짜별 기록(10-22~10-27)은 MooKKoDev 운영 기록입니다.
>
> 지움(11-10): 이 문서가 가리키는 하네스 `data/tools/`·`data/runtime/state/`·`data/runtime/native-bin/`·`data/runtime/launch/`는 지웠습니다(사용자 지시). `data/runtime/`에는 설정 파일 넷만 남았습니다.

Hub·MooKKoDev·AI 매니저·Studio는 Windows .NET 10에서 실행한다. Linux Docker는 제품 서버용이다. 관리 실행에는 WSL·tmux·OpenRig 데몬이나 Node 서버를 사용하지 않는다. 브라우저 JavaScript와 CI 개발 도구는 이 실행부와 구분한다.

## 기존 프로그램 적용

MooKKoDev는 기존 Hub 항목 `dev`, 기존 주소 `http://127.0.0.1:5288/`, 기존 화면을 사용한다. 별도 조회판 5295는 종료했다. Hub는 `src/MooKKo.Dev.Windows`를 버전별로 게시하고 `--config data/runtime/config.json`으로 실행한다. mookko.cmd도 같은 C# 실행판을 호출한다. 새 앱이나 새 담당을 등록하지 않는다.

설정·프로그램 토큰은 자기 저장소 `data/runtime/`, 내구성 원장은 `data/runtime/state/`, 담당별 Git 작업 폴더는 설정의 workspaceDirectory다. 토큰은 기존 승인된 프로그램의 것을 유지한다. AI 매니저와 Hub는 HTTP로만 연결한다. 정상 실행에서 이전용 WSL 명령을 호출하지 않는다. 일회성 source 확인도 먼저 실행 중인 배포판을 조회하므로 꺼진 배포판을 다시 켜지 않는다.

## 자료와 담당 문맥

기존 일감 5,484개, 담당 53개, 일감 전이 기록을 동일 ID로 이전했다. 실행이 실제 종료된 두 in-progress 수임은 완료로 위장하지 않고 동일 ID의 계속 작업으로 보존했다. 원본 Git HEAD·스테이징·미스테이징·일반 새 파일을 Windows private Git 작업 폴더로 이전했다. 공통 object cache는 읽기 전용이다.

역할 규칙·기존 세션 transcript·원문 지시·전이 기록·원본 CULTURE·서비스 목록·검토 보고서·등록된 세션 이력을 보존했다. 검증된 기존 사용자 출처만 사용자 지시로 인정한다. 이전 Linux 프로세스 정보는 Windows의 실제 실행 상태로 쓰지 않는다. 기존 자동 실행 metadata는 별도로 보존하며 활성화하지 않는다. Windows에서 지원하지 않는 이름과 링크는 실행되지 않는 형태로 보존한다. DB·키 링·로그인·백업 등 보호 경로는 읽거나 지우지 않고 원본에 남겼다.

reconciliation 세 담당은 승인된 규칙 커밋에 필수 AGENTS.md가 없어 기존 보류를 유지한다. 다른 커밋으로 임의 승인하지 않는다.

## 일감이 있을 때만 워커 실행

수임 가능한 실제 일감이 있을 때만 담당별 프로세스를 만들고, 한 담당은 한 번에 한 일감만 처리한다. 전역 동시 수는 가용 메모리와 외부 설정으로 조절한다. 일감이 없는 담당은 프로세스와 AI 자리를 유지하지 않는다. 작업 폴더·기록·세션 ID만 보존한다.

AI 매니저의 기존 leasesOnly 승인을 유지해 계정을 빌리고, 필요한 로그인 파일 하나만 해당 담당의 비공개 HOME에 전달한다. 기본 계정은 프로그램별·엔진별 명시적 허용과 Dev의 personalAccountEngines 설정이 모두 있어야 쓴다. 사용자가 기본 Codex 사용을 승인해 Dev에만 codex 허용을 적용했다. 로그인 갱신 충돌이나 응답 유실 시 원본을 덮어쓰지 않고 확인을 요구한다.

프로세스는 담당별 Windows AppContainer와 kill-on-close Job 안에서 실행한다. 다른 담당·관리 토큰·개인 HOME·loopback에 대한 접근 권한을 주지 않는다. Windows용 Codex/Claude와 C# WorkerHost만 실행하며 일반 호스트 실행으로 우회하지 않는다. CLI 내부의 중복 샌드박스는 끄며 WorkerHost가 AppContainer 토큰을 확인한 경우에만 시작한다. 워커별 HOME·HOMEDRIVE·HOMEPATH와 명령 실행 환경을 지정한다. Codex 내장 unified exec는 이 환경에서 홈 경로를 찾지 못하므로 내장 명령 도구를 끄고 같은 AppContainer 안의 C# stdio MCP run_command를 쓴다. 이 도구는 PowerShell을 직접 실행하고 출력 상한·기한·작업 경로를 제한한다. 호스트의 명령 대행이나 새 상시 서버를 열지 않는다. WorkerHost는 정상 시작 때 현재 게시판의 파일과 대조해 갱신한다.

한 턴이 끝나면 자식까지 종료한 뒤 AI 자리를 먼저 반납한다. Git 결과와 보고서는 그 뒤 기록한다. 대기 중 취소는 미수령 배정까지 회수한다. 실제 종료가 불명확하면 새 실행을 멈춘다. 시작 환경 오류는 같은 일감을 보존하고 배분을 멈추며 반복 실패로 대기열을 소모하지 않는다.

## 보고·보류·업데이트

워커의 명시적인 결과 보고서만 일감을 done/blocked/failed로 바꾼다. 후속 전달·검토 원장 제어와 원 일감 완료는 하나의 내구성 변경으로 기록한다. 검토 report/decision/task/process-qa/effect는 역할과 현재 실제 일감으로 제한한다. 사용자 답변은 원문과 출처를 보존하며 미응답을 승인으로 해석하지 않는다. 서비스 등록은 승인된 소유·역할 문서와 규칙을 읽어 Windows 작업 폴더와 담당을 만든다. 참조 검색과 변경 비교도 같은 C# 서버에서 처리한다.

AI 턴 성공을 QA 통과나 main 반영으로 계산하지 않는다. 커밋의 실제 엔진과 담당 경계를 대조하고 QA는 다른 엔진으로 배정해 정확한 후보 커밋에서 실행한다. 실제 CI와 관문 근거를 확인한 호스트만 서명 영수증을 발급하며, 통합 담당 요청의 정확한 SHA·서명·독립 엔진·기준 커밋·fast-forward를 확인한 프로그램만 제품 main에 반영한다. CI용 Python은 일회성 개발 도구이며 상시 서버가 아니다. 현재 allowTests=false이므로 CI를 실행하거나 새 통과 영수증을 발급하지 않는다.

Hub 재부팅 준비와 업데이트는 새 배분을 먼저 보류하고, 현재 워커뿐 아니라 Git 결과·보고서·자리 반납 확인까지 기다린다. 취소는 요청이 소유한 보류만 해제한다. 업데이트는 Hub의 windows-dev 드라이버가 같은 프로그램을 교체한다. 전체 멈춤은 실제 소유 프로세스 종료를 기다린다. Windows 부팅 ID가 바뀐 뒤에만 재부팅까지 보류를 자동 해제한다.

## QA 영수증·제품 반영의 정책 정본과 실패 격리(2026-10-24)

10-24 하네스 점검(`review/2026-10-24-harness-review.md`)에서 C# 실행부가 관문 목록·경로·예외 없이(이전된 pin 기록만 정책으로 알고) 영수증을 발급할 수 있고, 한 담당의 실패가 전체 배분을 멈추며, 부팅 재조정의 예외 하나가 호스트를 부팅마다 죽이고, 제품 push에 자격이 없음을 확인해 고쳤다.

- **정책 정본**: `productPolicyFile`(기본 `data/runtime/product-policy.json`, 상태 폴더 옆)은 `python -X utf8 tools/export-policy.py`가 `openrig_bridge.tooling.approved_policy`에서 만든다. 제품 규약 관문 목록(`gates`), 필수 서비스(`requiredServices`), 관문별 경로 패턴(`gatePaths`), 문서 전용 경로(`docOnlyPaths`), 관문 시작 시각(`gatesSinceById`), 예외 등록부(`gateExceptions`), 기준·검사 커밋(`baseCommit`·`checksCommit`)이 들어 있다. Linux 워커가 받는 정책과 같은 출처다. 파일이 없거나 관문·서비스가 비어 있으면 영수증을 발급하지 않는다. 이전된 pin 기록(`productPolicy` metadata)은 정책으로 쓰지 않는다. `validationToolsManifest`는 검사 도구 정본 `data/tools/manifest.json`을 가리킨다.
- **관문 판정은 호스트가 계산한다**(`Application/GateJudgement.cs`, Linux `skill_receipt.check_gates`와 같은 규칙). 영수증 기준 커밋(그 담당 작업 폴더에서 영수증·반영 기록이 있는 가장 가까운 first-parent 조상, 없으면 `refs/heads/main`과의 merge-base)과 후보 사이의 변경 경로를 `git diff --name-only`로 구하고(상한 5000, 넘으면 모든 관문 적용), 문서 전용 경로를 뺀 나머지에 경로 패턴이 맞는 관문을 적용 관문으로 본다. 적용 관문은 `na`로 넘길 수 없고, `pass`에는 그 관문 경로 안의 파일·줄 근거(후보 SHA에 파일이 있고 줄 번호가 길이 안)가 필요하며, `waived`는 만료 전·경로 범위 안의 ADR 예외가 필요하고, `fail` 하나면 거부한다. 영수증 시작 시각 뒤에 추가된 관문은 묻지 않는다. `DBDES-01`이 적용되는 `pass`는 QA·심사·수락 좌석의 검토 일감이 `design:approved`로 끝났고, 그 설계 커밋이 후보의 조상이며 `docs/data-model.md`를 바꿨고, 기준 커밋 뒤 첫 스키마 커밋보다 앞서는지 확인한다. CI 결과의 서비스 집합은 정책의 필수 서비스와 같아야 한다. 영수증 payload에는 정책 커밋·기준 커밋·변경 경로·적용 관문·판정이 들어간다.
- **이전 QA 일감의 입장**: 옛 실행기는 세션을 다시 띄울 때마다 새 rig ID를 썼기 때문에, 이전된 QA 요청 226건 중 118건의 `developer-rig:`가 53개 담당의 `sourceRigId`와 맞지 않아 거절됐다(점검 보고서 T-1의 "대상 커밋이 캐시에 없다"는 결론은 틀렸고, 411개 대상 커밋은 모두 캐시에 있다). rig를 모르는 요청은 등록된 개발 담당(QA·심사·수락 담당과 QA 담당 자신 제외)의 Linux 브랜치 `refs/heads/openrig/<담당>`가 그 커밋을 포함하고(보낸 좌석 `sourceSession`의 담당 우선), 커밋 트레일러의 엔진이 표기 엔진과 같을 때만 받는다. 읽기 전용 재현에서 226건 중 206건이 입장되고, 나머지(엔진 표기 없음 4·요청 담당 자신의 커밋 8·트레일러와 표기 엔진 불일치 5·담당 브랜치 밖 1·Windows 실행 경로 2)는 담당이 바른 표기로 다시 요청해야 한다.
- **제품 반영**: 반영 요청은 정책의 `checksCommit`(CI 기록과 영수증 payload 양쪽)과 `baseCommit` 조상 여부, main에 대한 fast-forward를 다시 확인한다. 원격 Git 작업은 전역 설정을 읽지 않으므로 `productCredentialHelper`(기본 `manager`, Git Credential Manager)를 `-c credential.helper=`로 명시한다.
- **워커 생존 확인과 Claude 설정 고정(보안 점검 S-1·S-2)**: 담당 프로세스 생존 확인은 TokenAppContainerSid의 필요 크기를 먼저 조회해 그 크기로 읽는다(8바이트 고정 버퍼는 실제 AppContainer에서 늘 실패해 검사가 죽어 있었다). Claude 턴은 `--settings`(API 주소 `https://api.anthropic.com`, 프록시 없음, TLS 검증, `apiKeyHelper` 없음, `disableAllHooks`, 프로젝트 MCP 끔)와 `--strict-mcp-config`를 받아 워커가 쓸 수 있는 설정 파일이 이를 덮지 못하고, 턴 시작 때 `.runtime\.claude\settings*.json`을 지운다(로그인·세션 기록은 유지). Codex는 `--ignore-user-config`와 `-c` 고정이다. 워커의 인터넷 능력과 로그인 파일이 같은 샌드박스에 있는 것은 남은 설계 과제다(호스트 전달 프록시 필요).
- **CI 실행(10-25, allowTests=true)**: QA가 통과를 보고하면 호스트가 먼저 후보 커밋의 zip 스냅숏에 trivy·osv-scanner·semgrep을 돌린다(`NativeWorkflow.RunHostScannersAsync`; 결과는 `data\runtime\validation\<run>\security\`, 워커가 쓸 수 없는 곳). Semgrep은 WSL이 아니라 `data\tools\semgrep\<판>\bin\semgrep.exe`(pip --target, 실행기 sha256 핀)로 돈다. 그 뒤 담당 컨테이너 안에서 `ci-tools/validate-native.py --host-scanners`가 제품의 자기 검사(비밀값·패키지 취약점·SBOM·서비스 시험)와 Graphify(`graphify-ci.py`, `data\tools\graphify\<판>`)를 돌린다. 컨테이너는 `data\tools`를 읽기 전용으로 받는다. 어느 단계든 실패하면 영수증은 없다. 워커 턴에는 `GIT_AUTHOR/COMMITTER_*`를 호스트가 넣는다: `MooKKoDev <담당> (<엔진>)` / `<담당-slug>@mookkodev.invalid`.
- **자리 대기 중 엔진 전환(10-25)**: AI 매니저의 queued 응답에 `alternativeEngine`이 있고 그 엔진이 `engineFallbacks`에 있으며 설치돼 있으면, 대기표를 취소하고 그 엔진의 `engineDefaults` 모델·추론으로 한 번 다시 요청한다(`WindowsNativeRuntime.CanSwitchEngine`, 원장 `engineFallback:<담당>`). QA 일감은 `developer-engine:`과 같은 엔진으로 바꾸지 않는다(독립 QA 유지). 되돌아오는 응답에 다시 다른 엔진이 적혀 있어도 두 번 바꾸지 않는다.
- **AI 매니저 끊김(10-26)**: 프로세스를 띄우기 전의 HTTP·시간 초과 오류(자리 요청·대기표 조회·취소)는 매니저 쪽 사정이라 담당 실패로 세지 않고 일감을 pending으로 돌려 다음 배분에서 다시 요청한다(원장 `managerOutage`). 대기표 취소·대여 반납이 실패해 `lease-uncertain`·`release-uncertain`으로 남은 실행은 1분마다 도는 재조정이 매니저가 답하는 즉시 정리한다(전에는 호스트 재시작까지 기다렸고, 10-25엔 매니저 배포 3회에 12개 담당이 멈추고 전체가 멈췄다).
- **담당이 직접 만든 커밋만 경계 판정(10-26)**: `WindowsGitTool.WorkerChangesAsync`는 턴이 만든 커밋(`after ^before ^origin/main`)의 경로만 모은다 — 비병합 커밋은 전체 diff, 병합 커밋은 `git merge-tree --write-tree` 자동 결과와 다른 부분(충돌 해결·손 편집)만. main에 이미 있는 커밋을 merge·rebase로 들여온 기준선 동기화는 담당 변경이 아니며, fast-forward만 한 턴은 수집할 것이 없다. 경계 밖 경로나 엔진 표기 불일치면 수집하지 않고 `.runtime/held-<run>.bundle`로 보존한 뒤 `git reset --mixed <before>`로 브랜치를 턴 시작 커밋에 되돌리고(파일은 작업 트리에 유지) `.runtime/context/held-commit-<run>.md`에 이유와 할 일을 적는다(보류된 커밋 위에 쌓인 다음 커밋은 번들 전제 조건이 캐시에 없어 영영 들어오지 못하므로). 판정·수집의 기준점은 턴 시작 커밋이 아니라 그 브랜치의 첫 부모 이력 중 객체 캐시가 이미 가진 가장 최근 커밋이다(`KnownBaseAsync`) — 커밋한 뒤 수집 전에 멈춘 턴의 커밋이 캐시에 없으면 다음 번들의 전제 조건이 빠져 영영 들어오지 못했기 때문이다(10-26 engine·developers/lead·monitoring/lead). 커밋의 엔진은 `작업자:`/Co-authored-by 트레일러와 호스트가 공급한 작성자 `MooKKoDev <담당> (<엔진>)`으로 판독한다(`CommitEngine(message, author)`, 둘이 어긋나면 판독 불가).
- **run_command의 환경(10-26)**: AI CLI는 MCP 서버(run_command)를 걸러진 환경으로 띄운다(Claude는 짧은 기본 목록만, Codex는 모르는 변수를 뺀다). 그래서 격리 실행부가 정한 Git 설정·Git 신원·HOME·DOTNET 값이 워커 명령에 닿지 않았다(Claude QA 턴의 git 실패). 컨테이너 안 실행기(WorkerHost `--plan`)가 시작할 때 자기 환경을 담당 HOME의 `.runtime\tools-environment.json`에 기록하고, run_command(`--tools`)가 매 명령의 PowerShell에 그 값을 되돌린다. 격리 환경에는 `SystemDrive`·`ProgramData`(담당 HOME 아래 전용 폴더)·`ALLUSERSPROFILE`·`ProgramFiles*`·`CommonProgramFiles`도 넣는다 — 없을 때 Windows 구성 요소가 `%SystemDrive%\ProgramData`를 글자 그대로 풀어 작업 사본 24곳에 `%SystemDrive%` 폴더를 남겼다(git 무시 대상이라 커밋되지는 않음).
- **멈춘 턴의 수임 반환(10-26)**: 실행이 시작된 뒤 호스트 재시작으로 멈춘 턴도 일감을 pending으로 돌린다(파일·CLI 세션은 다음 턴이 이어 씀). 1분 주기 재조정은 살아 있는 턴이 없는데 in-progress로 남은 수임(실행이 끝났거나 기록이 없음)을 되돌린다. 전에는 11:39 재시작으로 멈춘 developers/backend 일감이 주인 없는 진행 중으로 남아 Hub 업데이트 드레인이 끝없이 기다렸다.
- **계정 문제는 매니저에 알림(10-27)**: 턴이 사용량 한도(session/weekly/usage limit·rate_limit)나 로그인 실패(authentication_failed·OAuth session expired)로 끝나면 자리를 반납하기 전에 `POST /v1/leases/{id}/problem`으로 알린다(`AiManagerLeaseClient.ReportProblemAsync`, 원장 `accountProblem:<엔진>`). limit은 메시지의 풀리는 시각(`resetsAt`)을 함께 보내 매니저가 그때까지 그 계정을 배정에서 빼고, 일감은 그 시각까지 미룬다. login은 매니저 원본이 정상이면(`action: copy-again`) 사본이 오래된 것이라(한 계정에 동시 턴 둘 → 리프레시 토큰 회전) 1분 뒤 새 사본으로 다시 돌고, 아니면 30분 미룬다. 둘 다 담당 실패로 세지 않는다.
- **지어낸 대기 이름은 보낸 메시지의 답으로(10-27)**: 보고서가 메시지를 보내면서 blockedOn에 직접 만든 external 이름(예: `external:developers-design-approval`)을 쓰면, 그 이름은 풀어 줄 주체가 없어 영영 멈췄다(10-27 16건). 이제 같은 보고서가 메시지를 보냈으면 마지막 전달 일감을 기다린다(`WindowsWorkQueue.ReportAsync`). 사용자 결정(`external:user-*`), 프로그램 게이트(`external:mookkodev-*`), 기존 일감, 다른 일감이 이미 함께 기다리는 게이트는 그대로 둔다.
- **담당 간 파일 전달은 커밋으로(10-27)**: 각 담당 작업 공간(.runtime/context, TEMP)은 그 담당 AppContainer만 읽는다. 담당들이 자기 context의 ZIP·JSON 절대 경로를 보내고 '인계'를 기다려 RH-DM 원형 QA가 세 번 실패했다. 턴 안내에 넘길 파일은 자기 owns 경로에 커밋해 SHA·저장소 안 경로로 알리라고 적었다.
- **QA fail은 끝난 QA(10-27)**: QA가 관문을 fail로 판정하면 `GateJudgement`가 `실패로 판정된 규약 관문:`으로 거절하고, 그 예외로 보고서 전체가 버려져 QA 일감이 막히고 개발 담당은 결과를 못 받았다(wallet-qa, integration-qa 5건). 이제 영수증 없이 QA 일감을 끝내고(`outcome` done), 보고서 메시지에 요청 담당이 없으면 프로그램이 `[QA 결과 fail]` 메시지를 요청 담당에게 보낸다.
- **토큰 없는 로그인 파일은 버림(10-27)**: 로그인이 턴 중에 만료되면(11:11 Claude OAuth 만료) CLI가 토큰 없는 로그인 파일을 남기고, 검증 실패 표지(`refresh-*.json` review)가 그 담당의 다음 턴을 모두 막았다(operations/lead 14건). 토큰 같은 값이 하나도 없으면 지킬 리프레시 토큰이 없으므로 표지를 지우고 매니저 원본으로 다시 시작한다(`CredentialFile.CarriesToken`). 읽을 수 없거나 토큰 같은 값이 남은 파일은 그대로 확인 대기다. 어느 경우도 공용 계정에 다시 쓰지 않는다.
- **커밋을 가진 브랜치가 개발 담당(10-27)**: QA 요청의 developer-rig:가 가리키는 담당 브랜치에 후보 커밋이 없으면(운영툴 30ca4bef: rig는 operations/backend, 커밋은 operations/lead 브랜치) 커밋을 가진 개발 담당 브랜치로 담당을 정하고 엔진은 커밋 기록을 따른다.
- **충돌을 한쪽 판으로 정리한 병합(10-27)**: 병합 커밋에서 담당 변경은 Git 자동 병합 결과와 다르면서 두 부모 어느 쪽과도 다른 경로뿐이다(`WorkerChangesAsync`). 충돌을 main 판 그대로 받아 정리한 파일(search/lead가 사용자 결정 A로 AGENTS.md 등 통합 소유 3파일을 main 판으로 맞춤)은 새로 쓴 내용이 없어 경계 밖으로 보지 않는다. 새 문구로 고친 충돌 해결은 여전히 담당 변경이다.
- **AI 제공자 일시 오류(10-26)**: 턴이 "Selected model is at capacity"·rate/usage limit·overloaded·429/503 같은 제공자 쪽 오류로 끝나면(`NativeWorkerTurn.TransientProviderFailure`, 턴 결과의 `Failure`) 담당 실패로 세지 않는다. 자리를 반납하고 일감을 5분 뒤로 미루며(`deferredUntil`), 다음 턴이 같은 CLI 세션을 이어 쓴다(원장 `providerBusy:<엔진>`). 전에는 19분 일한 턴이 이 오류 하나로 담당을 멈췄다(operations/backend·platform/backend, 동시 20턴일 때).
- **QA 담당으로 가는 길(10-26)**: 담당은 자기 canSend 외에, 자기를 canSend에 둔 QA·심사·수락 담당에게도 보낼 수 있다(`WindowsWorkQueue.SendTargets`). 이전된 integration-qa는 integration에 답할 수 있었지만 어느 담당도 integration-qa에 보낼 수 없어, 규칙 커밋 반영의 QA 요청(927576d4)이 갈 곳이 없었다. 턴 안내의 담당 정보에도 실제로 허용되는 전달 대상이 canSend로 들어간다. 턴 끝 세션 연결(AttachAsync)은 5회 재시도 뒤 실패해도 결과 처리를 이어 간다(10-26 14:55 매니저 재시작에 끝난 턴 21건이 실패로 처리됐다).
- **영수증 판정 범위는 승인 기준 커밋 이후(10-26)**: 판정 기준점은 마지막 영수증·반영 커밋, main과의 공통 조상, 정책 baseCommit 중 후보에 들어 있는 가장 최근 것이다(`NativeWorkflow.ReceiptBaseAsync`, source `policy-base:<sha>`). baseCommit(d821d6c1)은 정책으로 승인된 내용인데 main 대비 스키마 파일 24개를 담고 있어, 그 위의 어떤 후보도 설계 승인 하나로 DBDES-01을 통과할 수 없었다(규칙 커밋 반영 QA ebd531fe). 기준 이후 범위(85커밋·87파일)에는 스키마 변경이 없다. QA 턴 안내에는 영수증 필수 관문 전체·적용 경로·추가 관문 판정 기준이 들어간다(`QaGateGuide`).
- **기준 커밋은 입장에서 먼저 확인(10-26)**: 영수증에는 정책 baseCommit이 후보의 조상이어야 하는데, 이 검사가 QA 턴이 끝난 뒤에야 돌아 하나뿐인 Claude 자리의 턴을 버렸다. QA 입장(`CheckQaAsync`)에서 자리를 빌리기 전에 `merge-base --is-ancestor`로 확인하고, 없으면 모든 후보가 같은 `external:mookkodev-runtime-admission — 후보에 승인 기준 커밋 …이 없습니다…` 게이트에 모인다. 10-26 현재 baseCommit d821d6c1은 openrig/integration에만 있어, 통합의 main 반영 뒤 각 개발 담당이 main을 받아 새 SHA로 다시 요청해야 한다.
- **QA 보고의 정책 밖 항목과 허용 안 된 전달(10-26)**: 정책 관문은 정확한 ID(`^[A-Z][A-Z0-9]*-\d{2}$`)와 모든 규칙을 그대로 강제하고, 담당 자체 점검 항목(예: `INT-G01`)은 함께 받아 두되 `fail`일 때만 막는다(전에는 그런 ID 하나로 integration-qa의 영수증 전체가 거절됐다). 보고서 messages 중 canSend 밖 대상은 전달하지 않고 summary에 이름을 적으며, 나머지 보고는 반영한다. `message:N`은 실제 전달된 번호로 다시 맞추고, 거부된 메시지를 기다리면 보이는 게이트가 된다.
- **막힘 자가 정리(10-26)**: 1분마다 도는 재조정 뒤 `HealBlockedAsync`가 이미 done인 일감을 기다리는 blocked 일감을 pending으로 돌리고(선행이 먼저 끝난 뒤 그 ID로 막힘을 보고한 21건이 영영 풀리지 않았다), 일감도 게이트도 아닌 설명 문장을 기다리는 일감은 같은 글을 `external:` 게이트로 바꿔 막힘 지도에 보이고 resolve로 풀리게 한다(25건). 워커 보고서의 설명형 blockedOn도 같은 규칙(`WaitTarget`)으로 저장한다.
- **QA 후보 폴더 정리(10-26)**: QA 턴마다 담당 폴더에 `candidate-<id>`(후보 SHA의 `clone --shared` 사본, 약 125MB)를 새로 만들고 지우지 않아 43개가 쌓여 있었다. 다음 후보를 만들기 직전 `NativeRepository.PruneCandidatesAsync`가 끝나지 않은 실행이 쓰지 않고 `git status --porcelain --untracked-files=all`이 비어 있는(무시 대상 빌드 산출물 말고는 바뀐 것이 없는) 이전 후보만 지운다 — 캐시에서 같은 SHA로 언제든 다시 만들 수 있는 작업 사본이라 시험 임시 폴더처럼 바로 지운다. 바뀐 파일이 있는 후보는 남기고 원장 `candidatePrune:<담당>`의 `kept`에 적는다.
- **QA 요청 판별과 개발 엔진 확인(10-26)**: QA 요청은 `commit:`+`developer-engine:`(호스트가 전달 커밋에 붙이는 태그)이거나 `kind:qa-request`·`qa:*`·`skills:planning-review`로 선언한 일감이다(`QaRequest`). `commit:`만 있는 조정 메시지는 담당 엔진으로 보통 턴을 돈다. 워커가 직접 쓴 QA 요청(PM 교차 QA 등)에는 `developer-engine:`·`developer-rig:`·`developer-node:`가 없으므로 커밋의 작업자 기록으로 개발 엔진을 정하고 브랜치 포함 대체 규칙(T-1)으로 생산 담당을 찾으며, 영수증 검증(`NativeWorkflow.VerifyAsync`)도 같은 기록을 쓴다. 독립 엔진 강제는 그대로다.
- **워커 턴의 도구와 Git 신원(10-26)**: Codex는 MCP 서버를 걸러진 환경으로 띄우므로 Git 작성자·커미터 신원을 `mcp_servers.mookko.env.*`로도 넘긴다(통합 담당이 `run_command` 안에서 네 변수가 모두 null임을 확인했었다). Claude 턴은 `--mcp-config`로 같은 mookko 서버(명령·인자·env)를 받는다 — 10-24 S-2 수정 뒤 Claude 턴에는 MCP가 하나도 없었고 Claude 자체 Bash는 MSYS 셸이라 AppContainer에서 명령을 하나도 못 돌렸다(10-25 monitoring/lead). 턴 안내에 MSYS 셸 불가, Python 대체 검사, `dotnet restore` 선행, 보류 커밋 안내를 적는다.
- **막힘이 보이게, 풀 수 있게(10-26)**: 입장·수집·보고 처리의 호스트 쪽 실패는 `FinishBlockedAsync`로 `external:mookkodev-runtime-<admission|report> — <원인>` 게이트에 걸어 막힘 지도에 보이고, `/api/job/depend resolve`가 곧 재시도다(전에는 참조 없는 blocked 45건이 어디에도 안 보였다). 워커 보고서는 `blockedOn:"message:N"`으로 이 보고서의 N번째 전달 일감을 기다릴 수 있고(그 일감이 done이면 자동 pending), `resolves:[{ref,note}]`로 조정용 `external:` 게이트를 스스로 푼다(`external:user-*`·`external:mookkodev-*` 제외, `WorkerMayResolve`; 해제 주체는 그 담당 seat로 기록). 자리·계정이 없는 엔진의 일감은 `DeferAsync(retryAfter)`로 10분(계정 전환 5분, 매니저 끊김 2분) 동안 `deferredUntil`을 받아 담당의 다른 준비된 일감 뒤로 물러나며, 혼자 남으면 그대로 돈다.
- **실패 격리**: 워커 시작·턴·결과 처리 실패는 그 담당만 멈추고(`PausedRoles`, `roleProblem:<담당>`), 15분 안에 3개 담당이 실패하면 호스트 문제로 보아 전체를 멈춘다(`runtimeProblem`). 담당을 다시 시작하면 그 기록을 지운다. AI 매니저가 자리 요청에 409 `switch-account`로 답하면 일감을 보존하고 다음 배분에서 다시 요청한다(`switchAccount:<엔진>`). 부팅 재조정은 실행 건별로 격리해 실패한 건만 `failed`로 적고 그 수임은 `blocked`로 돌리며 호스트는 계속 뜬다. heartbeat는 연속 3회 실패까지 견딘다. 워커가 쓴 로그인 파일은 JSON 객체이고 원본의 최상위 항목을 모두 갖고 토큰 값이 있을 때만 공유 계정에 반영하고, 아니면 `review` 표시를 남겨 그 담당의 다음 실행을 막는다.

## 확인 범위와 미완료

기존 5288에 Windows C# 실행판을 적용했다. AI 매니저의 Dev 프로그램별 0 상한을 지워 기존 엔진 풀의 배분을 따르게 했다. 작업용 계정의 사용 한도는 유지하며 사용자가 승인한 기본 Codex만 추가로 사용한다. 기존 일감의 실제 provider 호출을 시작했고 Windows 명령 실행 홈 경로 오류에 영향받은 일감은 완료 처리하지 않고 같은 ID로 다시 배분했다. 새 C# 명령 도구를 통해 developers/backend·integration 기존 일감의 실제 파일 조회 명령이 종료 코드 0으로 실행됐다. 교체 때 소유 provider/WorkerHost 프로세스와 매니저 자리 모두 0으로 회수됨을 대조했다. 실제 작업 결과와 사용자 확인은 일감별 기록을 따른다.

사용자 요청에 따라 이번 실제 적용에서는 시험 모음·벤치마크·추가 provider 시험을 실행하지 않았다. Release 빌드와 게시, 기존 포트의 실제 시작·운영 상태를 확인한다. 사용자가 확인하지 않은 동작은 통과로 기록하지 않는다.

| 기준 | 판정 | 근거·남은 범위 |
|---|---|---|
| 기존 주소의 Windows C# 관리 서버 | 충족 | Hub의 기존 dev 항목과 5288에 적용, health backend=windows-csharp |
| 원본 일감·53개 작업 폴더·문맥 이전 | 부분 충족 | Git·일감·전이·문맥 이전. 보호 경로 원본 유지, 모든 보조 증거 원장 동등성 미검증 |
| 유휴 프로세스·자리 회수 | 충족 | 실제 기존 일감의 턴 종료 뒤 소유 프로세스와 해당 AI 자리 반납을 운영 상태로 대조. 세션 ID·실제 작업 폴더만 보존 |
| 담당 격리·실제 provider 도구 실행 | 부분 충족 | AppContainer 안에서 기존 일감의 실제 파일 읽기·명령 실행 확인. 별도 격리 공격 시험은 미실시 |
| 보류·재부팅·업데이트 | 부분 충족 | 기존 Hub 버튼과 C# 제어·결과 처리 대기 연결. 실제 전체 작업 drain 사용자 확인 미실시 |
| 전체 업무 전환 구현 | 부분 충족 | 서비스 등록·검토 제어·사용자 결정·참조·변경 비교·CI 서명·프로그램 main 반영을 C# 실행 경로에 연결. 10-24 점검에서 관문 판정 장치·정책 정본·push 자격이 빠져 있던 것을 보완(위 절). 실제 전체 흐름(QA 영수증 → main 반영)은 allowTests=false·Claude 자리 0으로 아직 실행하지 못함 |
| 독립 QA·사용자 확인 | 미확인 | 미실시. 전체 전환 검증 미완료 |

조회 성능의 기존 자체 측정은 같은 관측 자료를 사용했을 때 상태 생성 중앙값 407.15ms, C# revision 캐시 21.29ms, 변경 없는 304 응답 0.15ms였다. 브라우저 렌더링·실제 AI 작업·전체 시스템 성능을 증명한 수치가 아니다.

기존 시험 임시 자료 네 경로는 사용자 지시에 따라 휴지통으로 보냈고 각 경로의 $I 기록을 확인했다. 실제 일감·작업 폴더·이전 문맥·원본 보호 자료는 유지한다.

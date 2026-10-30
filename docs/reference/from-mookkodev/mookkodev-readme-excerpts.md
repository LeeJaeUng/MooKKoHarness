# MooKKoDev README에서 가져온 절

원본: C# 하네스 MooKKoDev README.md(커밋 daf975d, GitHub LeeJaeUng/MooKKoCLI). 2026-10-30 MooKKoDev 철거 전에 넘겨받음. OpenRig·Windows 실행 전용 내용은 참고로만 읽는다.

### 공용 규칙과 검사 기준

- 모든 역할은 `<linuxInstallRoot>/product-rules/<rulesCommit>/`의 공용 규칙 묶음을 읽습니다. `role-docs.json`이 정한 역할별 필수 문서는 이 묶음의 절대 경로로 세션에 전달됩니다. 묶음은 승인된 Git 커밋에서 원자적으로 만들고 읽을 때 원문 해시와 파일 목록을 확인합니다.
- 작업 사본에 규칙을 덮어쓰거나 규칙 적용만을 위한 담당별 병합 일감을 만들지 않습니다. 일일 점검과 막힘 복구도 같은 묶음을 씁니다. 기존 역할의 커밋·미커밋 파일은 보존합니다. 제품 코드의 필수 검사·독립 QA·push 조건은 계속 적용됩니다.
- 새 서비스의 전용 `AGENTS.md`가 공용 기준에 아직 없으면 그 담당 작업 사본의 커밋된 파일을 읽습니다. 미커밋·staged 변경과 링크는 거부하고, 전용 지침은 공용 조건에 추가하며 공용 조건을 낮출 수 없습니다.
- 공용 규칙과 검사 코드를 함께 승인했으면 외부 `config.json`의 `productPolicy.commonCommit` 하나로 `rulesCommit`과 `checksCommit`을 정합니다. `baseCommit`은 업무 변경 범위의 기준입니다. 공용 pin과 서로 다른 분리 pin을 동시에 지정하면 설정 오류입니다. 최신 HEAD를 자동 승인하지 않습니다.
- 원격 반영 검사도 역할별 `publish.json`에 정책 값을 복제하지 않고 `<linuxInstallRoot>/product-policy.json` 한 곳을 읽습니다. 시작할 때 기존 역할의 정책 사본은 이 파일 참조로 옮기며, 승인된 pin 값은 보존합니다. 파일이 사라지거나 형식이 잘못되면 이전 역할 값으로 통과하지 않습니다.
- 이전 분리 pin 설정도 읽습니다. 기존 작업 사본 대조·담당별 규칙 병합 방식이 필요한 이전 배포에서만 `sharedProductRules: false`로 지정합니다. 공용 묶음에 필수 문서가 없거나 변조·링크가 발견되면 실행을 보류하며, 역할에게 병합을 시켜 공용 오류를 해결하지 않습니다.

검증: `python -X utf8 -B -m unittest tests.shared_rules_test`.

공용 Windows/WSL 실행기는 Windows 자식 프로세스를 로컬 프로그램 폴더에서 시작합니다. WSL에서 부른 Windows CLI가 `\\wsl.localhost` 작업 폴더를 물려받아 다시 WSL을 호출할 때 멈추는 문제를 이 한 곳에서 막습니다. Linux의 작업 사본 위치는 별도의 `--cd`로 유지합니다.

### 정기 점검 (일일·주간·월간)

- 화면 서버가 매일 `dailyReview.hour`(기본 12시) 이후 첫 작업 순회에서 읽기 전용 담당 `daily-review`(화면 이름 **일일 점검**)에게 점검 일감을 하나 만듭니다. 기간은 전날 정오부터 그날 정오까지이고, 같은 날은 한 번만 만듭니다. 전체 멈춤 중에는 만들지 않으며, 놓친 날은 가장 최근 하루만 만듭니다.
- 일감에는 제품 main·담당 브랜치(`openrig/*`)·MooKKoDev master 커밋 표(담당·파일 수·시험 동반·일감 ID, 최대 `maxCommits`개)와 그 기간 일감 요약, 어제 지시서 상태, 점검 지침이 들어갑니다.
- 기존 `daily-review` 담당 하나가 일일·주간·월간을 맡습니다. 일일은 기존 정오~정오, 주간은 월요일 정오에 직전 월요일 00시~이번 월요일 00시, 월간은 1일 정오에 직전 달 전체를 평가합니다. `periodicReview.offsetMinutes`(기본 한국 시간 540), `weekly`·`monthly`의 `enabled`·`hour`를 외부 설정으로 바꿉니다. 일일을 꺼도 주간·월간은 독립적으로 동작합니다. 처음 켜면 최근 마감 기간부터 시작하고, 이후 놓친 주·월은 순서대로 한 기간씩 보충합니다. 전체 멈춤 중에는 생성하지 않습니다.
- 점검은 잘된 점·못한 점·해야 할 일·지난 조치의 실제 개선 결과를 씁니다. 커밋/시험 수는 활동량이며 완료나 보안 통과를 대신하지 않습니다. 이전 보고서와 원래 일감·QA·정확한 커밋·실제 반영 근거를 대조하며, 자료가 없으면 미확인입니다.
- 발견 사항은 영문 `key`에서 만든 고정 `RV-…` 번호로 추적합니다. 같은 문제를 주간·월간에서 다시 발견해도 원래 번호와 일감을 유지하고 관찰 기록만 추가합니다. 최초 상태·기대 결과·근거·담당·목표 날짜·완료 조건·효과 확인 방법을 보존합니다.
- 워커는 공유 도구 `mookko-review <UTF-8 JSON파일>`로 보고·판정·하위 작업·효과 판정을 native 제어 일감에 남깁니다. `list [항목번호]`, `reports [주기:기간]`은 전체 기록을 읽습니다. 형식의 정본은 `openrig_bridge/review_protocol.py`의 워커 지침입니다. 제어 일감은 워커를 깨우지 않고 프로그램이 처리하며, 기존 실행기의 블록 문법을 쓰지 않습니다.
- 프로그램은 보고서를 PM에게 전달하고, PM이 항목별 수용·기각·보류와 이유를 제출하면 수용 항목의 실제 담당 일감을 만듭니다. 이미 있는 일감은 ID로 연결합니다. 보류는 재검토 조건을 남기며, 범위·비용·공개 계약·보안 예외 등 사용자 결정이 필요한 항목은 자동 수용하지 않습니다. PM이 보고서를 끝내고 판정을 빠뜨리면 판정 확인 일감을 한 번 보냅니다.
- 보내기 의도를 먼저 원장에 기록하고, 고정 native ID로 생성한 실제 일감의 수신자·내용·태그를 확인해야 전달 완료입니다. 응답 유실·재시작은 같은 ID로 복구합니다. 오류는 화면과 원래 담당의 확인 일감에 남으며, 입력을 고친 새 메시지에 `retryOf`를 넣으면 기존 오류와 연결됩니다. 원장과 보고서·판정·전후 관찰 기록은 `windowsHome/reviews/ledger.json`에 원자적으로 보관합니다. native 대기열이 작업 실행 상태의 정본입니다.
- 하위 구현·QA·회신도 `task` 입력의 `finding`·`parent`로 원래 항목에 연결합니다. native `parent:` 회신과 원래 QA 일감을 가리키는 `skill-qitem:` 회신도 담당 신원을 대조해 연결합니다. 개발만 끝나면 QA 전달을 확인하고, 최종 QA 회신이 오면 점검 담당에게 효과 확인 일감을 보냅니다.
- 일감 `done`, QA 통과, main 반영, 개선 효과를 구분합니다. 개선 확인/부분 개선에는 현재 회차의 실제 QA 일감·정확한 SHA·다른 실제 엔진 신원·전체 검증 근거·main 반영과 개선 전후 관찰을 모두 대조합니다. cherry-pick은 검사한 변경과 동일한 패치인지 확인합니다. 관련 작업이 없으면 관찰 중이며, 실패·취소·미검증은 개선 완료가 아닙니다. 후속 작업이 더 생기면 효과를 재확인하고, 재발하면 기존 이력을 보존한 새 조치 회차를 엽니다.
- 코드가 없는 일감 막힘 해소 등은 `verification: process`와 `processTargets`(실제 대상 일감 ID → 기대 상태)로 등록합니다. 최초 실제 상태를 보관하고, 작업을 맡긴 실제 native node와 다른 엔진의 QA가 `process-qa`를 제출합니다. 프로그램이 원래·현재 상태와 QA 이후 변동을 직접 대조해 전부/일부 개선을 구분합니다. 코드 커밋이 연결되면 이 방식으로 완료할 수 없으며 PM이 `verification: code`로 올려 기존 코드 QA·main 반영을 거칩니다. 코드 검증을 process로 낮추는 것은 거부합니다.
- 담당은 화면 서버가 뜰 때 한 번 등록합니다(제품 `servicesBaseRef` 기준 작업 사본, 권한 read). 각 주기의 `enabled`로 생성 여부를 정합니다. 기존 담당 ID와 역할별 AI 설정은 유지합니다.

- 단축키 `G D`로 정기 점검을 엽니다. 실제 일감을 누르면 오른쪽에 상세가 열립니다. `GET /api/reviews`의 `kind`·`year`·`month`·`q`·`page`로 찾고 `period`로 본문과 후속 상황을 읽습니다. 기존 `/api/daily-review`도 유지합니다.
- 화면 **정기 점검**에서 일일·주간·월간, 연도·월, 보고서 내용·개선 항목 검색으로 찾습니다. 목록은 서버에서 20건씩 나누고, 선택한 보고서 본문만 가져옵니다. 개선 항목은 미해결·기한 초과·관찰 중·개선 확인·재발로 좁히며, 다른 점검의 현재 미해결 항목도 함께 보여줍니다. 담당 일감·판정 이유·최초 상태·목표·전후 효과를 펼쳐 볼 수 있습니다. 기존 일일 보고서와 날짜 링크는 유지합니다. [정기 점검 UI](docs/daily-review-ui.md)

검증: `python -X utf8 -B -m unittest tests.daily_review_test tests.daily_review_view_test tests.periodic_review_test`, `node tests/openrig_review_ux_ui_test.cjs`. 실제 native 연결은 `python -X utf8 -B tools/verify-periodic-review.py`로 별도 daemon·새 시험 저장소에서 확인하며 실제 AI나 제품 일감을 만들지 않습니다.

### 막힘 정리 (10-20)

막힘을 전담하는 층이 셋 있습니다(`openrig_bridge/unblock.py`, 작업 순회마다). (1) 판단이 필요 없는 것은 프로그램이 바로 풉니다: 끝난 일감이나 큐에 없는 참조에 걸린 일감은 대기로 되돌리고(전이 기록에 이유), 서로 기다리는 고리는 가장 최근에 걸린 일감 하나를 되돌려 끊습니다(`dependencies.cycles`, 확인함 기록). (2) 막힘 보고를 `GET /api/state`의 `blockage`에 둡니다: 사슬 뿌리마다 종류·담당·뒤에 기다리는 일감 수·기다린 시간·담당 좌석이 안 도는 이유. (3) 처리할 막힘(AI 매니저 자리 대기·사용자 결정이 아닌 뿌리)이 있는 동안 **막힘 정리 YYYY-MM-DD HH:MM** 일감(`kind:unblock`)을 만듭니다 — 열린 막힘 정리 일감이 없고 직전 일감을 만든 지 `unblock.minIntervalMinutes`(기본 10분)가 지났으면 바로. 자리 대기만 남으면 만들지 않습니다. 받는 쪽은 전담 담당 `unblock`(화면 이름 **막힘 정리**, 읽기 전용, 모든 담당에게 보낼 수 있음, 기본 모델 Claude Fable 5.1 · high — 설정 화면에서 바꿀 수 있음)이고, 그 자리가 아직 등록되지 않았으면 PM이 받습니다. 자리는 첫 보고 때 뒤에서 자동 등록됩니다(일일 점검과 같은 방식). 담당은 뿌리별로 그대로 대기(AI 매니저 자리 대기는 손대지 않음)·담당 재확인·닫음·우선순위 올림을 적고 닫습니다. 화면 일감 목록의 **막힘 정리** 탭이 이 일감(`kind:unblock`)만 모아 보여 줍니다. `unblock.enabled`를 끄면 보고만 남기고 일감은 만들지 않습니다.

### 막힘 복구 워커

`recovery`(화면 이름 **막힘 복구**)는 CI·검증 환경·QA 연결·담당 경로 문제로 막힌 일감의 공통 원인을 처리합니다. `config.json`의 `recoveryWorker.enabled`를 켜고 `sourceRepo`에 MooKKoDev 소스 저장소를 지정하면 화면 서버 시작 때 독립 Linux CLI 작업 사본과 고정 역할을 등록합니다. 기본값은 꺼짐이며, `scanSeconds`는 15~3600초 범위입니다. 실행 중 서버에 별도 등록 명령을 쓰지 말고 설정 후 화면 서버를 다시 시작합니다.

- 선행 작업을 따라 같은 원인의 연쇄 보류를 묶어 native 복구 일감 하나를 만듭니다. 정상 진행 중인 선행 작업, 사용자가 멈춘 담당, 복구 워커 자신의 보류는 새 장애로 보내지 않습니다.
- 같은 장애가 남아 있는 동안 재시작 후에도 중복 생성하거나 완료·취소된 복구를 자동으로 다시 열지 않습니다. 원인이 사라졌다 다시 발생하면 새 회차로 접수합니다. 같은 장애에 새 증거가 생기면 화면에서 해당 복구 일감을 재시도합니다. 최신 영향 목록은 `MooKKoOpenRig/recovery-incidents.json`에 남습니다.
- 워커는 기존 개발 엔진 선택·모델·사용 상한을 따릅니다. 워커별 옵션으로 변경할 수 있고 전체 멈춤·워커 멈춤도 그대로 적용됩니다.
- CLI 수정은 별도 사본에서 시험·커밋·독립 검토 후 기존 업데이트 절차로 전달합니다. 제품 코드는 원래 담당에게 요청합니다. 원본 일감의 상태, QA, 규칙, 계정 상한을 자동으로 우회하지 않습니다. 역할 지침은 [rules/recovery.md](rules/recovery.md)입니다.

검증: `python -B -m unittest tests.recovery_worker_test`.


## 긴급 멈춤

- 전체 멈춤 = 실행 데이터 폴더의 `PAUSED` 파일입니다 (`%LOCALAPPDATA%\MooKKoDev\runtime\PAUSED`). 이 파일이 있으면 새 일감을 시작하지 않습니다.
- `mookko pause [역할]`은 `mookko.cmd`가 Python 없이 처리합니다. `mookko resume`·`mookko kill <역할>`은 Python 이 있으면 사람 확인(boot)을 거칩니다. Python 이 없거나 Python 길이 실패하면(사람 확인 거부는 제외, 프로그램을 `MOOKKO_PIN_PROGRAM`·`MOOKKO_HOME` 으로 고정해 둔 때도 제외) `mookko.cmd`가 처리합니다 — resume 은 PAUSED 파일만 지우고(실행기는 띄우지 않음), kill 은 명령줄·시작 시각을 확인하고 taskkill 결과를 봅니다. 화면의 '전체 멈춤'·'강제 중지'도 화면 처리 코드를 불러오지 못한 상태에서 확인을 통과한 POST 로 동작합니다.
- 실행기가 시작 단계에서 멈추면 `system-errors.jsonl`과 `PROGRAM_ERROR.json`에 남깁니다. 시작 단계는 코드 불러오기, 설정·엔진·필수 템플릿 읽기입니다.
  - 일감은 대기열에 그대로 두고 실패로 세지 않습니다.
  - 30초부터 최대 10분 간격으로 다시 시도하고, 같은 오류는 한 번만 알립니다.
  - 화면 위 '지금 다시 시도' 또는 `mookko start-retry`로 바로 다시 시도합니다.
- 꺼진 역할에 남은 일감은 보관만 하고 실행기를 띄우지 않습니다. 하루 한 번 알립니다.

## 일감 전달 규칙

1. 보내면 항상 받는 역할의 `runtime/roles/<역할>/jobs/`에 날짜·시간 이름의 일감 파일을 먼저 씁니다.
2. 받는 역할이 쉬고 있으면 그 자리에서 실행기를 띄워 바로 시작합니다. 역할마다 세션은 한 번에 하나이고, 서로 다른 역할은 동시에 일합니다(동시 실행 개수 제한 없음).
3. 일하는 중이면 파일로 쌓이고, 일감이 끝나면 들어온 순서대로 다음 일감을 꺼내 새 세션으로 처리합니다. 우선순위는 없습니다. 다시 묻는 일감(`<ID>~a1`)과 확인 목록에서 이어 보낸 일감(`<ID>~d1`)은 원래 일감의 차례를 이어받습니다.
4. 일감을 꺼낼 때마다 아직 필요한지 프로그램이 먼저 봅니다. 필요 없으면 AI를 부르지 않고 "자동으로 해결되어 건너뜀"으로 끝내고, 보낸 쪽 메모·작업 카드 목차·QA 장부에 남깁니다.
   - 맡긴 QA 항목이 모두 이미 닫힘·해결 확인인 `fix`
   - 같은 작업의 검사 요청이 대기열에 여러 개면 맨 앞 하나에 합쳐 최신 코드로 한 번 검사 (나머지는 "앞 검사 요청에 합쳐짐")
   - 멈춤으로 끝난 작업에 늦게 온 `task`·`fix`·`review-request`(task 는 보낸 쪽에 알림 일감), 통과로 끝난 작업에 늦게 온 `fix`, 마지막 검사가 시작되기 전에 온 `review-request`
   - 통과로 끝난 작업에 늦게 온 `task` 는 버리지 않고, 아직 필요한지 먼저 보라는 메모를 붙여 처리합니다(통과 전에 보낸 새 지시를 잃지 않게).
   - 사용자가 보낸 일감과 다시 묻는 일감은 건너뛰지 않습니다.
5. 앞 일이 끝나야 하는 일은 `[[send … after=<일감 ID 또는 같은 답변 send 의 name>]]`로 보냅니다. 일감 대신 결과 상태로도 기다립니다: `qa:<작업>/<QA>`(통과·main 반영), `merged:<SHA|태그>`, `contract:CT-n@committed`, `bundle:<프로필>`. 총괄 일감 ID 는 `qa:`로, 다른 범위 편집 역할의 일감 ID 는 `merged:job/<ID>`(끝나고 main 에 들어감)로 바뀝니다. 다른 범위 결과를 기다린 편집 역할에는 'main 동기화'(`<ID>~u1`) 프로그램 일감이 먼저 들어가고, 같은 범위 다른 개발 브랜치의 앞 일감 결과는 시작 때 프로그램이 합칩니다. 그 일감은 받는 역할의 `waiting/`에 비켜 두어 그 역할의 뒤 일감을 막지 않고(서로 기다리는 교착 방지), 앞 일감이 끝나면 원래 파일 이름 그대로 `jobs/`에 넣어 원래 차례로 처리합니다. 앞 일감이 실패·건너뜀이면 시작하지 않고 실패 목록으로 옮겨 기다리던 역할(메모)·보낸 역할(알림 일감)·사용자에게 알리며, 그 일감을 기다리던 일감도 이어서 멈춥니다. 화면 대기열 탭에서 취소할 수 있습니다.
6. AI는 답변 끝의 `[[send to=… kind=…]] … [[/send]]` 블록으로 다른 역할에게 보냅니다. 보낼 수 없는 상대는 막히고, 다음 턴에 실패 사실이 전달됩니다.
7. 멈추지 않게: 실패는 사용자 알림함·MooKKoDev 기록(`runtime/notifications.jsonl`)과 보낸 쪽 메모로(Windows 알림은 쓰지 않음), 빈 답·보낼 것 없는 답은 두 번 다시 묻고 그래도 안 되면 상위 역할과 사용자에게, 오래 걸리는 일감(`limits.longRunMinutes`, 기본 60분)과 오래 기다리는 일감(`limits.longWaitMinutes`, 기본 240분)은 한 번씩 사용자와 상위 역할 메모로 알립니다(`limits.longRunNotifyParent: true`면 상위에게 알림 일감도). 화면에는 역할마다 대기 수·앞 일감 대기 수·지금 하는 일·마지막 결과가 보입니다.

## 결과가 사라지지 않게 (AI 답 뒤의 처리)

개발 담당이 구현 일감을 마치거나 완료 보고를 보내기 전에 프로그램이 `config.json`의 `developerChecks`를 실행합니다. 기본값은 변경에 영향을 받는 서비스의 기존 CI 계획·경계 검사·식별자 분석·서비스 빌드/시험이며, `"mainChecks"`로 설정하면 main 검사 목록을 그대로 사용합니다. 검사 명령은 사용자가 관리하는 설정에서만 가져오고 기존 낮은 무결성 격리와 일회용 Git 사본을 사용합니다. 실패하면 보고와 QA 요청을 보류하고 같은 개발 역할에 보완 요청을 보냅니다. 두 번의 보완 뒤에도 실패한 완료 보고는 전달하지 않고 상위에 실패 사실을 알립니다. 실제 실행에서 빈 검사 목록·격리 실패·서비스 검사 계획 누락은 통과가 아닙니다.

설계는 기존 총괄이 합니다. 총괄은 `[[plan scope=pay grade=light|normal|important version=1 design="pay/docs/design.md" validation="pay/docs/validation.md"]]등급 근거[[/plan]]`로 계획을 등록합니다. 중요 변경은 기존 완료 조건(C-n)과 커밋한 두 문서가 필요합니다. 총괄의 `[[plan-verdict scope=pay version=1 aspect=design decision=pass|fail]]근거[[/plan-verdict]]`와, 프로그램이 기존 QA에 맡기는 `plan-review`의 검증 계획 판정이 모두 통과해야 구현합니다. QA는 예정·실제 구현 엔진을 피하며, 실제 구현 엔진이 검토 엔진과 같아지면 사전 검토를 다시 요청합니다. 등급이 없는 구현 일감은 보류하고 해당 총괄에 `planning`을 보냅니다. 별도 설계 역할은 만들지 않습니다. 설계·검증 문서나 완료 조건이 바뀌면 계획 버전을 올립니다.

공용 관문·품질 요약·서비스 QA 기준은 개발 시작 때 cycle에 고정해 개발과 QA가 함께 사용합니다. 개발 자체 점검은 고정된 공용 관문을, QA는 여기에 고정된 서비스 관문을 더해 판정합니다. 새 기준을 쓰려면 범위 총괄이 `[[quality-refresh scope=pay]]사유[[/quality-refresh]]`로 새 cycle을 열어 검증 계획을 다시 검토합니다. 요약은 MooKKo 정본의 관문·MAINT 체크 항목 원문에서 발췌하고, 같은 서비스의 수용 후 수정 확인된 QA 지적은 기존 원장에서 새 작업 프롬프트에 붙입니다. 모범 구현은 정본 `role-docs.json`의 `qualityExamples.common` 또는 서비스별 목록에 `path`, `sha`, `approvedBy`를 등록한 경로만 표시합니다. 등록 전에는 미등록으로 표시합니다. 요약·계획 문서·지적 전달 길이는 `limits.qualityBriefChars`, `planDocumentChars`, `lessonCount`, `lessonChars`로 조절합니다.

이 상태 형식은 2입니다. 실패 보고 보류와 계획 검토 상태를 모르는 이전 판으로 적용을 되돌리지 않습니다. 실제 AI·MooKKo CI 실행과 독립 재검토는 격리 셀프테스트 결과와 별도로 확인합니다.

- **블록 읽기**(`mookko/blocks.py` 한 곳):
  - 블록은 줄 처음에서 시작하고 닫는 태그 `[[/종류]]`가 있어야 합니다. 속성 값은 따옴표 안이면 `]`도 씁니다.
  - 닫히지 않은 블록이나 형식이 틀린 블록은 '읽지 못한 블록'으로 보고를 보류하고 다시 묻습니다. 뒤 블록을 삼키지 않습니다.
  - 엔진 답이 여러 메시지면 마지막만 처리합니다. 앞 메시지에만 있는 블록은 찾아서 다시 묻습니다.
- **단계별 처리**(`mookko/turn.py`): 엔진이 끝나면 답 원문 전체(`turns/<ID>.answer.md`)와 결과(`<ID>.result.json`)를 먼저 저장합니다. 그다음 순서대로 처리합니다.
  1. 블록을 장부에 반영합니다. 장부도 일감 ID로 한 번만 반영합니다.
  2. 보냅니다. send마다 sendKey를 `runtime/outbox`에 적습니다.
  3. 보완 요청·위로 올리기를 합니다.
  4. 카드·목차를 기록합니다.
  - 실행기가 끊겨도 AI를 다시 부르지 않고 남은 단계부터 하며, 같은 send를 두 번 보내지 않습니다.
  - 후처리에서 오류가 나면 `failed/postprocess/`에 둡니다. `mookko retry <역할> --job <ID> --post` 또는 화면의 '후처리만 다시'로 처리합니다.
- **다시 묻기(보완 일감 `<원 ID>~aN`, kind=amend)**:
  - 빠진 것만 채우게 묻습니다. 보류한 보고 원문, 직전 답, 이미 보낸 것, `mookko show` 안내를 싣습니다.
  - 같은 엔진·계정이면 직전 세션을 잇습니다.
  - 빠진 것이 채워지면 보류했던 보고는 프로그램이 이어 보냅니다(AI가 다시 쓰지 않음).
  - 두 번 물어도 안 되면 보류 보고를 '판정 보완 실패' 메모와 함께 보내고, 상위·PM·사용자에게 올립니다.
- **보내기 실패와 보고 누락**:
  - 받을 수 없는 상대, `qa-report`의 점수·관문 형식 오류는 실패한 것만 다시 묻습니다.
  - 답이 필요한 일감에 보낸 것도 `[[wait]]`도 없으면 다시 묻습니다.
  - 남은 일감 없이 30분(`limits.stallMinutes`) 지난 작업은 PM·사용자에게 한 번 알립니다.
- **작업 사본 미커밋**:
  - 같은 일감을 이어 하는 중이면 합치지 않고 그대로 이어 합니다.
  - 다른 일감이면 그 일감을 `parked/dirty/`에 세우고, '미커밋 정리' 시스템 일감(`<ID>~c1`)을 `priority/` 대기열에서 먼저 돌립니다. 깨끗해지면 세운 일감이 원래 차례로 돌아갑니다.
  - 한도·끊김·시간 초과로 되돌린 일감은 이어 하기 기록(`resume`)을 남깁니다. 다음 시도는 진행 기록 끝부분, 작업 사본 상태, 앞 시도 뒤 커밋을 붙여 이어 합니다.
- **시작 합치기 충돌**: 실패가 아닙니다.
  - 역할을 `SYNC_BLOCKED`로 세워 시스템 일감만 진행하고 한 번 알립니다.
  - 그 역할에 충돌 해결 일감(`<ID>~m1`, `priority/`)을 넣습니다. 프로그램이 병합을 시작하고, 충돌이 그 역할 담당 파일뿐이면 AI 가 충돌만 풀어 `git add`, 커밋은 프로그램이 합니다. 다른 담당 파일이 섞이면 병합을 되돌리고 PM·사용자에게 올립니다.
  - 원천 브랜치가 바뀌거나 `mookko sync-retry <역할>`(화면 '합치기 다시 시도')로 다시 시도합니다.
- **형식 보호**:
  - 모르는 값이 든 장부는 그 작업(스레드)의 일감만 `format-hold/`에 세웁니다. 다른 작업은 계속하고, 장부를 고치면 감시가 되돌립니다.
  - 읽을 수 없는 일감 파일은 `quarantine/`으로 옮기고 한 번 알립니다.
- 일감 ID는 프로세스 사이에서도 단조 증가합니다(`seq.json`). 같은 밀리초에 만들어도 만든 순서대로 정렬됩니다.

## QA 판정 (`team/templates/service-qa.json`의 `qa`)

QA가 `kind=qa-report score=<점수> gates=<pass|fail>`로 보내면 프로그램이 판정합니다.

- 관문 통과 + 90점 이상 + 미해결 0 → `qa-pass` (범위 소유자가 기록 파일을 커밋하면 프로그램이 확인하고 push → main 반영)
- 점수·관문은 넘었고 판정·확인만 남음 → `qa-followup` (회차로 세지 않음)
- 막는 이유가 이의·재정 대기뿐 → `qa-followup` '재정 필요' (회차로 세지 않음), 사용자 결정 대기 항목이 있으면 작업이 `user-wait`
- 그 밖 → `qa-fail` (총괄이 고칠 점을 담당에게 넘김)
- 3회차까지 통과 못 함, 같은 항목 2회 재발, 점수 2회 연속 정체, 확인 회차 안전 상한(10) → `qa-hold` (확인 목록). 거기서 "멈춤"을 고르면 `qa-stop`

**cycle (묶음 5):** (작업, QA 역할)마다 회차를 cycle 로 묶습니다(`runtime/threads/<작업>.json`).
- 첫 검사 때 판정 정책(passScore 등)과 관문 목록(기준은 검사 커밋의 파일)을 고정합니다. 기준·정책을 바꾸면 다음 cycle 부터 적용됩니다.
- 통과·멈춤으로 끝난 작업에 같은 작업으로 새 지시가 오면, 그리고 확인 목록에서 계속·지시를 고르면 새 cycle 이 열립니다. 재발 기준은 그때 장부로 다시 잡습니다.
- 검사가 진행 중인 작업에 PM 이 일을 더하면 `cycle=join|new`를 써야 합니다.
- 2회차부터 범위는 열린 항목 재확인과 직전 검사 뒤 변경입니다. 새 제안·보통·낮음 항목은 `next-cycle`로 남아 통과를 막지 않고, cycle 이 끝날 때 총괄이 `[[next … decision=adopt|drop]]`로 정합니다(adopt 면 PM 에 후속 작업 제안).
- QA 보고는 100점 미만이면 감점표(`[[deduct area= points= items=]]`)가 있어야 합니다. 합계는 100-점수, 근거는 장부 항목·관문 ID 입니다.
- 관문 판정은 회차마다 새로 봅니다(지난 회차 판정이 남지 않음). 이번 변경 줄 밖의 기존 위반은 `existing`으로 받아 통과를 막지 않습니다.
- 같은 검사 커밋·같은 장부로 다시 온 검사 요청은 건너뜁니다.

**장부 규칙:** 관문·보안·자금(AUTH·WEB·DATA·MONEY·CFG·CSB)·막음·높음 항목은 사람만 닫습니다. QA 동의나 총괄 재정으로 닫으려 하면 '사용자 결정 대기'가 되고, 확인 목록에 항목 단위 질문(수정 지시·예외 승인·기존 위반 원장·별도 작업·보류)이 올라갑니다. 보류(defer)는 해결이 아닙니다: 사람 대상이면 사용자 결정, 다른 담당 몫(`to=`)이면 외부, 그 밖은 총괄 재정을 기다립니다. 판정은 총괄이 배정한 담당만, 이의는 항목마다 1회, 닫힌 항목은 QA 가 다시 열지 못합니다(같은 문제면 `dup=`).

**확인 목록:** (작업, QA)마다 열린 항목은 하나입니다(새 hold 는 갱신). 대기 중 검사 요청은 `parked/qa-hold/`에 세우고 QA 보고는 '추가 보고'로 붙습니다. 결정은 버전이 있어, 그 사이 결과가 바뀌었거나 사람이 먼저 정했으면 AI 판단은 '늦게 온 권고'로만 남습니다. 사람 대상 항목이 있으면 'AI 처리'를 막습니다.


## 보안 경계 (P0, 1·2차 재검토 반영)

- **엔진 격리 (낮은 무결성 + Job Object):** 엔진(claude·codex·muse)과 그 자식(빌드·시험), 프로그램의 restore·main 반영 전 검사(mainChecks)는 자기 토큰을 복제해 무결성만 낮춘 토큰으로, 빠져나가기(breakaway)를 막은 역할별 Job Object 안에서 돕니다. 엔진이 끝나거나 실행기가 죽으면 Job 째 끝나 남은 자식도 끝납니다(KILL_ON_JOB_CLOSE). 낮은 무결성 표시는 쓰기가 꼭 필요한 곳에만 붙입니다(P0R2-B3):
  - 작업 사본(worktreesDir 안, `.git` 이 파일인 사본)과 그 worktree 의 git 폴더
  - 편집 역할이면 공용 .git 중 `objects`·`refs/heads/<자기 브랜치 폴더>`·`logs/refs/heads/<자기 브랜치 폴더>` 만 (공용 config·config.worktree·info·hooks·packed-refs·refs/remotes 는 보통 무결성). 역할 브랜치는 `mookko/<역할>/work` 라 자기 폴더를 갖습니다 — 다른 역할 브랜치가 든 폴더나 refs/heads 전체는 표시하지 않고 멈춥니다(P0R3-M8)
  - 이 표시들(작업 사본·git 폴더·objects·ref 폴더)은 **그 역할 턴 동안만** 붙고, 엔진 Job 이 끝나면 후처리 git 전에 걷습니다 — 턴 중 AI 가 남긴 명시 표시까지. 다른 역할이 턴 중에 같은 폴더(objects 등)를 쓰고 있으면 그 역할이 끝날 때 걷고, 비정상 종료로 남은 표시는 실행기가 시작할 때 걷습니다(P0R3-H4)
  - runtime 밖 `<runtime>-low/<역할>`(scratch·TEMP·전용 NuGet 캐시·dotnet 홈·엔진 전용 홈)
  - 전용 clone·공식 루트·runtime·data·적용 스냅숏·사용자 프로필의 .claude·.codex·공유 계정 홈에는 붙이지 않습니다(붙이려 하면 격리 준비가 멈춤). 실행기가 시작할 때 예전 판이나 사고로 그런 곳에 붙은 표시를 찾아 걷어 내고 알립니다.
  - 격리하지 못하면 AI·검사를 돌리지 않습니다(검사는 '보류'로 30분 뒤 다시).
  - 엔진 Job 은 이 사용자·SYSTEM 만 열 수 있고 보통 무결성 표시(쓰기·읽기 올려다보기 금지)가 붙어 낮은 무결성 엔진은 Job 손잡이를 열지 못합니다. 실행기 시작·`mookko kill` 때 같은 이름 Job 을 끝내고, 엔진이 끝난 뒤 Job 안에 프로세스가 남거나 확인하지 못하면 턴 뒤 검사 없이 일감을 실패로 보류하고 알립니다(P0R3-M14)
  - `mookko sandbox low|job|show`: `low` 가 기본입니다. `job`(보통 무결성 + Job)은 사람 확정 위조·비밀값 검사 우회·계정 홈 변경이 가능해져 `--accept-risk` 로 사람이 위험을 받아들여야만 쓰입니다(P0R2-M10). 엔진이 낮은 무결성에서 실제로 도는지는 P7 에서 확인합니다.
- **엔진 계정 홈 (P0R2-B2·B5):** 엔진은 사용자·Orchestra 의 공유 홈이 아니라 엔진·계정마다 MooKKo 전용 홈(`<runtime>-low/<역할>/home-<엔진>-<계정>`, 기본 계정도 같음)에서 돕니다. 실행마다 설정 파일을 정해진 내용으로 쓰고 허용 목록(인증·고정 설정·세션 기록 `projects/*/*.jsonl`·코덱스 `sessions/**/*.jsonl`·뮤즈 data)만 남기며(지시 파일·기억(memory)·그 밖은 지움), 인증 파일만 원래 홈에서 복사해 들이고 끝나면 지웁니다. 남긴 파일은 턴 끝에 해시를 runtime 에 기록하고, 다음 준비 때 달라졌으면(쉬는 동안 다른 역할이 낮은 무결성 폴더에 씀) 홈을 비우고 세션을 잇지 않으며 알립니다(P0R3-M10). 한계: 턴 중에는 인증 복사본이 낮은 무결성 폴더에 있어 동시에 도는 다른 역할 엔진이 읽을 수 있습니다 — 역할별 SID·AppContainer 분리는 P7-2 전 조건입니다(P0R3-L9·M10).
  - 원래 홈으로 되돌려 쓰지 않습니다: 형식 검사만으로는 정당한 토큰 갱신과 '구조가 맞는 다른 계정 토큰으로 바꿔치기'를 가를 수 없기 때문입니다. 엔진이 턴 중에 갱신했는지는 일감 기록(`authRefreshed`)에만 남깁니다(P7 회전 확인 근거).
  - 대신 턴 전에 원래 홈의 만료 시각(클로드 `claudeAiOauth.expiresAt`, 코덱스 `access_token` 의 exp)을 읽어, 기준(`limits.authMinRemainingMinutes` — 분, 숫자 또는 `{"claude": 30}` 처럼 엔진별, 없으면 턴 제한 시간 + `limits.authMarginMinutes`(15분))보다 짧거나 읽지 못하면 **그 일감에서만** 그 계정을 빼고 다음 계정·엔진으로 갑니다(로그인 차단으로 기록하지 않음 — 설정을 바꾸면 다음 일감부터 바로 다시 판정). 뺄 때는 계정·남은 시간·필요 시간·바꿀 설정을 한 번 알리고, 남은 계정이 모두 만료 임박이면 실패가 아니라 30분 뒤 다시 보는 대기(`authExpiring`, `limits.authExpiryRetryMinutes`)입니다. 통과·제외 모두 일감 기록 `authGate` 에 남은 시간·기준을 남깁니다(P0R3-M15). 기준을 턴 제한보다 낮추면 턴 중에 토큰이 회전해 원래 홈과 어긋날 수 있습니다 — 실제 남은 수명은 P7-1 에서 기록합니다.
  - 되돌려 쓰는 길은 없습니다. 엄격한 되돌려쓰기(허용 키 정확 일치·계정 동일성 확인)는 P7 에서 토큰 회전이 실제로 확인될 때만 설계합니다. 지금은 갱신본이 정상 갱신처럼 보이는지(모든 깊이의 키·형, 필수 값, 계정 값, 만료가 늘었는지, 갱신 토큰만 바뀌지 않았는지)를 진단으로 기록만 합니다.
- **읽기·외부 전송 경계 (P0R2 B — 낮은 무결성은 쓰기만 막는다):** 표시 없는 사용자 파일은 낮은 무결성에서도 읽히고 네트워크도 열려 있습니다(셀프테스트가 가짜 비밀값으로 확인).
  - `mookko sandbox protect`(사람만)는 인증·기록 폴더(`.claude`·`.claude.json`·`.codex`·`.ssh`·`.git-credentials`·gh·aws·azure·docker·Orchestra 계정·기록 폴더, 뮤즈 config/data, 설정 `secretPaths`)에 '보통 무결성 + 읽기·쓰기 올려다보기 금지' 표시를 붙입니다. 사용자의 보통 무결성 프로그램은 그대로 읽고, 낮은 무결성 엔진은 읽지 못합니다. 실제(모의 아닌) 엔진 준비는 이 보호가 없으면 멈춥니다 — 사람이 `mookko sandbox accept-read-risk --accept-risk` 로 받아들이면 그대로 돕니다(그때 보호 없던 경로 목록을 범위로 저장하고, 그 밖에 보호 없는 곳이 생기면 다시 막음, 해제는 `mookko sandbox revoke-read-risk`). `mookko sandbox show` 가 폴더별 상태를 보여 줍니다. protect 는 붙이기 전 원래 표시를 기록하고 `mookko sandbox unprotect` 가 그대로 되돌립니다 — protect 뒤 Orchestra 의 클로드·코덱스·뮤즈를 한 번씩 돌려 깨지면 unprotect 합니다. 실행기는 준비 때마다 '임시 파일 + 이름 바꾸기' 저장으로 사라진 표시를 다시 붙입니다(P0R3-M3·M12·M13·L8).
  - 클로드: 모든 역할에서 `WebFetch`·`WebSearch` 와 위 인증 폴더의 `Read` 를 금지하고, 모든 역할의 `Read`·`Grep`·`Glob` 을 작업 폴더(`./**`)로만 엽니다(작업 카드·runtime 기록은 `mookko show` 로 읽음) — **이 허용은 경계가 아닙니다**(낮은 무결성은 읽기를 막지 않음, 실제 경계는 위 protect). 클로드는 `--setting-sources user --strict-mcp-config` 로 돌아 작업 사본의 .claude 설정·.mcp.json 을 읽지 않고(빠지면 적용 거부), 커밋된 .claude/·.mcp.json·.codex/·.muse/ 는 턴 뒤 보류합니다(P0R3-M2). 뮤즈: 웹 가져오기·curl·wget·Invoke-WebRequest 를 거부합니다. 코덱스 read-only 는 디스크 읽기를 막지 않아 PM·판단은 클로드를 권장하고, 코덱스로 돌리면 알리고 기록합니다.
  - 남는 한계: 엔진 자신은 자기 계정 인증을 읽고, 모델이 읽은 내용은 그 제공자에게 갑니다. 코드를 실행하는 역할(개발·총괄·통합·QA·인수)의 빌드·시험·훅은 네트워크와 표시 없는 파일 읽기가 열려 있습니다 — AppContainer 격리·`mookko build/test`·신뢰 훅 고정은 P7-2 전 조건이고, 그때까지 그 역할의 실제 실행은 하지 않습니다 — 실제 runtime 에서 그 역할 일감은 엔진을 부르지 않고 대기(`codeRolesBlocked`)하며, 사람이 `mookko code-roles allow --accept-risk` 로 켜야 돕니다(`block`·`show`, P0R3-M11).
- **현재 설치판 실행:** 엔진 턴·후처리·프로그램 일감은 현재 설치판과 실제 실행판의 VERSION·경로 및 정상 적용·자체 검사 기록을 확인합니다. 옛 재검토 차단과 일회 허락 명령은 워커 실행에서 제거했습니다. 그 사유만으로 미뤄진 원래 일감은 자동으로 재개하며, 다른 대기와 사용자 멈춤은 보존합니다.
  - 프로그램 검토 이력은 업데이트 관리 기록으로 보존하고 평상시 일감 실행에는 사용하지 않습니다. 검토 기록을 추가하거나 철회해도 일감 대기열과 실행판을 바꾸지 않습니다.
  - 설치판·실행판 불일치와 코드 실행 권한·격리·제품 QA·고정 커밋 검사·인증·한도·의존성 대기는 유지합니다.
  - 되돌리기: `mookko apply --to-last-pass`(가장 최근 통과판으로, 상태 형식이 내려가면 거부). 상태: `mookko program-status`.
  - 턴 기록 `turns/<일감>.cmd.json` 에 적용 SHA·실제 엔진 실행 파일(.cmd 셔임이면 cmd.exe 가 아니라 그 대상, `via`)·버전(PE 리소스에서 읽음 — 실행하지 않음)·해시·읽은 MooKKo 규칙의 기준 커밋과 근거(신뢰 SHA·작업 폴더 HEAD·미커밋·규칙 파일별 해시·확인 여부)·자동 업데이트 끔(기록에 실패하면 턴을 시작하지 않음)(클로드 `DISABLE_AUTOUPDATER=1`, 코덱스·뮤즈는 끄는 설정을 확인하지 못해 해시로 대신)을 남기고, runner.json 과 작업 카드의 턴 기록(turns.jsonl)에도 적용 SHA 가 있습니다.
- **규칙 출처:** 담당표(owners.json)와 문서 지도(role-docs.json)는 전용 clone 작업 트리(fetch 로 갱신되지 않음)가 아니라 프로그램 fetch 가 기록한 신뢰 SHA 에서 읽습니다. OpenRig 모드에서는 Windows 실행기가 돌지 않으므로, 설정 검사(`mookko _validate`, 적용·업데이트 때) 전에 전용 clone 을 시간 제한(90초)·자격 도우미 창 없는 프로그램 fetch 로 받아 신뢰 SHA 를 새로 기록합니다. 받지 못하면 마지막 기록으로 검사하고 경고를 남깁니다. 기록 키는 clone 경로라, 앱 폴더를 옮기면(MooKKoCLI → MooKKoDev) `load_config` 가 한 번 새 경로 키로 옮깁니다(`runtime/git-guard/moved-home.json`). 신뢰 SHA 에서 꺼내는 것(신뢰 훅·담당표·문서 지도·.gitleaks.toml·restore 의 main 줄)은 commit→tree→blob 마다 해시를 다시 계산해 대조하고, 다르면(공용 objects 의 위조 객체) 쓰지 않고 `runtime/git-guard/integrity.jsonl` 에 남겨 알립니다(P0R3-H3). PM·판단 턴 전에는 repo 잠금 안에서 전용 clone 을 신뢰 SHA 로 맞추고 읽을 규칙 파일이 확인한 객체와 같은지 보며, 작업 폴더 밖 규칙(적용판 rules/)은 원문을 프롬프트에 붙입니다(P0R3-M1·H1). 규칙 문서 경로(@docs)는 그 역할의 작업 사본을 가리키며, 그 사본에서 담당 밖 문서를 고치면 턴 뒤 담당 검사가 위반으로 봅니다.
- **사람 확인:** CLI(boot·cli 입구), `jobs.send` 의 사용자·프로그램 이름 발신, 사람 이름으로 기록하는 공용 함수(결정·항목 결정·설정·해석 확인·조건 승인·사용자 결과·restore 허락·비밀값 재구성·오탐 허용·범위 해제·git 설정 받아들이기·재검토 통과·엔진 옵션 저장·저장공간 정리·멈춤 풀기·다시 실행·후처리 다시·push 다시·합치기 다시·대기 취소·세션 새로 시작·역할 멈추기·지시(요청 R 만들기 전))는 그 프로세스가 사람 쪽인지 봅니다 — AI 작업 환경 변수, 무결성이 보통보다 낮음, 엔진 Job 안, 부모 사슬에 살아 있는 실행기(runner.json 시작 시각까지 같은 것)면 거부하고, 확인하지 못해도 거부합니다. 재검토 통과·1회 허락·마지막 통과판으로·읽기 보호(protect·unprotect·accept-read-risk·revoke)·격리 방식·코드 실행 역할 켜기도 같습니다. 엔진 PATH 에는 보기 명령(show·status·roles)만 받는 `bin/ai/mookko.cmd`·`bin/ai/mookko`(sh) 를 넣고 전체 `mookko` 는 뺍니다. 사람이 mookko 를 실행할 때 그 프로세스는 현재 폴더를 import·실행 파일 검색에 넣지 않습니다(`-P`, `NoDefaultCurrentDirectoryInExePath`, taskkill·git 전체 경로 — git 을 못 찾으면 이름만으로 부르지 않고 오류). 다만 **명령 프롬프트(cmd.exe)는 `mookko` 를 칠 때 현재 폴더의 mookko.cmd 를 PATH 보다 먼저 찾습니다** — 작업 사본 폴더에서 mookko 를 치지 않거나, 사용자 환경 변수로 `NoDefaultCurrentDirectoryInExePath=1` 을 둡니다(`mookko check`·`mookko sandbox show` 가 없으면 경고, PowerShell·Git Bash 는 해당 없음). 작업 사본 맨 위에 새로 생긴 실행 확장자(PATHEXT) 파일은 턴 뒤 보완 사유입니다(P0R3-L3).
- **화면 서버:** Host 가 정확히 `127.0.0.1:<포트>`·`localhost:<포트>`인 요청만 받습니다. POST 는 `application/json`, 같은 출처 Origin, 서버 메모리 토큰(`X-MooKKo-Token`), 연결 상대 프로세스가 사람 쪽(위와 같은 판정, pid 를 모르면 거부)일 때만 받습니다. 토큰은 `mookko ui` 가 연 주소 조각(`#t=…`)의 1회용 값(10분)을 `/api/session` 으로 바꿔서만 받고 화면 JS 메모리에만 둡니다(쿠키 없음). 화면을 새로 고치면 `mookko ui` 로 다시 엽니다. 결정·설정·해석 확인·조건·사용자 결과·범위 해제·정리·강제 중지는 화면에서 한 번 더 확인합니다. 화면 처리 코드를 못 불러온 긴급 상태에서도 멈춤·재개·강제 중지는 확인을 통과한 POST 로만 됩니다(역할 ID 검사는 이 셋에만, 나머지 id 는 화면 API 가 봄). GET 은 쿼리만 보고 본문은 버립니다. Content-Length 는 ASCII 숫자 7자리·1MB 까지(아니면 400·413, 본문을 읽지 않고 닫음), 소켓 읽기 10초 제한에 요청 하나(요청 줄·머리글·본문)를 30초 안에 다 받아야 하고, 동시 연결 64·동시 처리 32개까지 — 멈춤·재개·강제 중지와 고위험 POST 는 따로 둔 칸(8)을 써서 토큰 없는 GET 이 칸을 다 잡아도 503 이 나지 않습니다. 목록 길이(`limit`)는 200 까지(P0R3-L1·L2). 격리가 job 모드면 화면 맨 위와 실행기 시작 알림에 그 위험을 띄웁니다(L11). 모든 조작은 `runtime/user-actions.jsonl`에 경로(화면·CLI)·PID·시각과 함께 남습니다.
  - 한계: 같은 Windows 사용자로 보통 무결성에서 도는 다른 프로그램(엔진 격리 밖)이 브라우저 메모리를 읽거나 화면을 조작하면 막지 못합니다.
- **프로그램 git:** 프로그램이 부르는 모든 git 은 신뢰 위치의 git 으로, 먼저 지키는 파일(작업 사본 `.git` 파일·worktree 의 commondir·config.worktree·gitdir·공용 config·config.worktree·info/attributes·info/exclude)을 프로그램이 남긴 스냅숏과 비교해 다르면 되돌립니다(`runtime/git-guard/restored.jsonl`). 그 사본 전용 파일을 되돌렸으면 턴 위반, 공용 파일이면 누가 했는지 모르므로 사용자 알림입니다. 처음 보는 설정은 위험 키(hooksPath·fsmonitor·filter·textconv·diff/merge 드라이버·sshCommand·credential 등)가 없을 때만 기준으로 받습니다. 작업 사본의 `.git` 이 폴더↔파일로 바뀌거나, 기록한 사본 아래에서 `.git` 이 없어지면(위 폴더 저장소로 넘어가지 않게) 프로그램 git 을 멈춥니다. 기록 없는 연결 사본은 공용 .git 의 worktree 등록과 맞을 때만 받아들입니다(P0R3-L13). 작업 사본별 설정(`config.worktree`)은 읽지 않게 `extensions.worktreeConfig=false` 이고 AI 의 push 막기(`pushurl`)는 공용 config 에 둡니다. 모든 프로그램 git 에 `GIT_CONFIG_COUNT` 로 고정값(fsmonitor·서명 표시·서명 커밋·alternateRefsCommand·ext 프로토콜·attributesFile·safe.bareRepository)을 붙입니다 — `include.path` 는 git 이 명령줄의 빈 include 를 거부해 고정할 수 없어, 공용 config 를 보통 무결성으로 두고 받아들이기 전 include 를 검사하는 것으로 대신합니다. ls-remote·push 는 역할 사본이 아니라 전용 clone 에서 기록된 origin 주소로 돕니다(P0R3-H4). `-c core.hooksPath=<프로그램 fetch 가 기록한 신뢰 SHA 의 scripts/git-hooks 를 runtime 에 복사한 폴더>`·`-c core.fsmonitor=false`·(네트워크가 아니면) `-c credential.helper=`, diff·log·show 에 `--no-ext-diff --no-textconv` 를 붙여 AI 가 심은 훅·fsmonitor·filter·textconv 를 실행하지 않습니다. 환경은 AI 환경 수준이고 fetch·push·ls-remote 만 전체 환경(자격 증명)을 씁니다. 추적 안 된 훅 파일은 보완 사유입니다. 사람이 전용 clone 설정을 직접 바꿨으면 `mookko git-config-accept [경로]` 가 차이와 확인 값을 보여 주고, `--confirm <확인 값>` 일 때만(그 사이 바뀌지 않았을 때만) 받아들입니다(P0R3-L12). 보기 전용 명령(`mookko show --diff`)은 지키는 파일을 건드리지 않는 읽기 전용 git 으로 돕니다. MooKKoDev 소스 저장소(사람 것)의 git 은 이 보호 밖이지만 신뢰 위치 git·훅·fsmonitor·자격 도우미 끔으로 부릅니다.
- **턴 뒤 검사가 정본:** 클로드 금지 도구·뮤즈 낱말 판정은 **보조 방어층**입니다(클로드 접두어 규칙은 `git commit -F msg --no-verify` 같은 뒤쪽 인자를 막지 못함). 정본은 턴 뒤 프로그램 검사입니다 — 커밋마다 담당 경로(owners.json, 신뢰 SHA), refs/ 전체 비교(자기 브랜치가 턴 시작 커밋 뒤로 가지 않고 옮겨짐·refs/stash·팀 밖 새 브랜치·프로그램 밖 태그·다른 이름공간은 위반, origin 추적 ref 는 프로그램 fetch 기록으로 되돌림, 다른 역할 브랜치가 앞으로 가지 않고 옮겨지면 알림), 원격 비교(턴 시작 때와 다르고 프로그램 push 기록에 없는 원격 `mookko/**` 는 위반 — HEAD 를 거치지 않은 커밋도, main 은 이 턴·이 저장소에서 만든 커밋이면 위반이고 아니면 알림, ls-remote 두 번 실패면 알림), 비밀값 검사. **실패로 끝난 턴도 같은 검사를 하고**, 다시 실행해도 검사 시작점(headStart)을 이어 갑니다(P0R3-M9). 역할 브랜치 끝은 프로그램이 옮길 때와 주인 턴의 검사 뒤에만 기록하고, 턴 시작 때 기록 뒤 남이 얹은 커밋(빨리 감기 포함)은 위반·알림이며 그 턴의 담당 검사 범위에 넣습니다(P0R3-M8).
- **AI 환경 변수:** 엔진에는 허용 목록(시스템 경로·사용자 폴더·프록시(사용자:비밀번호@ 는 뺌)·DOTNET/NUGET/MSBUILD·MOOKKO_*)만 넘기고, 이름에 TEST·CONNECTION·SECRET·TOKEN·PASSWORD·API_KEY·CREDENTIAL·CRED·AUTH·COOKIE·PRIVATE·PAT·_KEY 가 든 값은 언제나 뺍니다(설정 `aiEnvAllow` 로 더할 수 있음).
- **비밀값:** 저장·화면에 쓰는 AI 답·진행 기록·원본 출력(JSON 줄은 값을 풀어 가린 뒤 다시 씀, 뮤즈 글 조각은 합친 뒤)·events·프롬프트 사본·로그·알림·커밋 제목·전환 기록·엔진 오류는 비밀값 같은 문자열(PEM(끝 없는 것 포함)·sk-·ghp_·xox·AKIA·JWT·Bearer·Google API·GitLab·npm·Hugging Face·Stripe·SendGrid·Slack/Discord 웹훅·주소의 `사용자:비밀번호@`·SAS `sig=`·`"Secret": "…"`·`DB_PASSWORD=`·`Password=`·auth/cookie/credential 등 비밀 이름 키)을 `[가림]`으로 바꿉니다. 블록 표기는 구조를 지킨 채 가립니다(태그 사이 글은 따로, 태그 안은 속성 값만 — 큰따옴표·작은따옴표·따옴표 없는 값 모두, P0R3-L18). 자를 때는 가린 뒤 자릅니다. 블록 해석과 하위로 보내는 본문은 확실한 형식만 가린 사본(`turns/<ID>.parse.json`)으로 해 정상 지시(`credentials: include`·`OAuth: Google`·`SameSite=Lax`)가 `[가림]` 으로 바뀌지 않게 하고, 화면·answer.md·result.json 사본만 이름=값까지 가립니다. `auth` 이름은 `auth_token`·`auth-key`·`auth_header` 꼴만 봅니다(P0R3-M17). 커밋 검사는 Gitleaks 8.30.1(버전 정확히 일치, 언제나 `--config`(origin/main 의 .gitleaks.toml 또는 기본 규칙), `--ignore-gitleaks-allow`, 빈 ignore, `--cc --text --no-textconv`, 빈 attributesFile)로 하고, 없으면 확실한 형태만 막고(여러 줄 PEM 개인 키는 (커밋, 파일)마다 더한 줄을 이어 붙여 보고, 커밋 메시지는 전체 글도 봄 — P0R3-M16) 이름=값 꼴은 경고만 합니다. **push 전 검사는 gitleaks 8.30.1 이 꼭 있어야 하며 없으면 push 를 보류합니다 — 설치는 사용자 몫이고 P7 전 조건입니다.** 검사기·git 이 실패하거나 범위 기준이 없거나 범위 안에서 .gitleaks*·.gitattributes 가 바뀌거나 작업 사본에 신뢰 SHA 와 다른 .gitleaks* 가 있으면 보류합니다. 걸리면 보고를 보류해 값을 지우게 하고, 이미 커밋된 이력은 아직 push 하지 않은 개발 브랜치에 한해 사용자가 `mookko secret-rebuild <역할> <깨끗한 SHA>`로 다시 만듭니다 — 알림이 비밀값이 처음 들어간 커밋의 바로 앞 SHA 를 알려 줍니다(같은 커밋을 가진 다른 브랜치도 그 브랜치의 명령으로). 그 브랜치를 after 로 기다리는 일감은 합치지 않고 재구성될 때까지 기다립니다. GitHub 비밀값 보호(GH013) 거절도 재구성 명령을 안내합니다 — push 전 로컬 검사가 찾은 것(`secret-local`)·검사를 못 한 것(`scan-blocked`)은 GH013 문구 없이 따로 안내합니다(P0R3-L19). 오탐은 `mookko secret-allow <지문>`.
- **역할 권한:** 접근 프로필에 클로드 `bypassPermissions`(permission 'all')를 쓰는 역할을 두지 않습니다. 클로드 금지 도구(`--disallowedTools`, 개발·총괄은 `scripts/git-hooks` 편집도)는 명령줄에 들어가고 `turns/<일감>.cmd.json` 에 실제 명령줄(가림)이 남습니다. 뮤즈 승인은 요약의 낱말로 판정합니다 — 셸 연결·치환은 거부하고, 낱말은 정규화합니다(따옴표·^ 제거, 묶은 짧은 옵션 나누기, git 처럼 줄인 긴 옵션 접두어, `이름=값` 양쪽, 경로 정규화·실행 파일 경로는 이름만, git 전역 옵션 건너뛰기). 뮤즈의 write·edit·create 는 정규화한 경로가 작업 폴더 안일 때만(짧은 이름 `~숫자`·끝 점·공백·스트림 `:`·장치 이름·UNC 거부), 머리말은 `Run: …` 처럼 한 낱말만이고 콜론이 더 있으면 거부합니다(P0R3-M10·L23). 설정 검사는 핵심 금지 항목(push·reset·config·--no-verify·WebFetch·WebSearch·인증 폴더 Read, 뮤즈 git -c·core.hookspath·curl 등, 코덱스 `-c tools.web_search=false`)이 빠지면 적용하지 않습니다. 코덱스에는 명령 수준 금지가 없습니다(샌드박스 쓰기 폴더로만 막음). 코덱스 답은 JSON 출력의 마지막 답이 정본이고, `-o` 답 파일은 실행 전에 지우고 출력에 답이 없을 때 실행 뒤 새로 생긴 것만 씁니다(무작위 이름, P0R3-M10). 코덱스 세션 기록(AI 가 쓸 수 있음)에서 읽은 사용량은 Orchestra usage.json 의 사용률을 낮추는 쪽만 쓰고 계획·새 항목은 만들지 않습니다(P0R3-L10).
- **패키지 복원:** restore 는 엔진과 같은 격리에서, 작업 사본이 있는 모든 역할(개발·QA·인수·총괄·통합)이 자기 NuGet 폴더로 돌고(dotnet 이면 `-noAutoResponse`·`-p:ImportProjectExtensionProps=false`·`-p:ImportProjectExtensionTargets=false` — obj 의 nuget.g.* 를 읽지 않음), 커밋된 패키지 파일만 다룹니다(하위 폴더의 NuGet.config·packages.lock.json·global.json 포함). 마지막 성공과 merge-base(HEAD, origin/main) 중 최신 뒤 바뀐 줄이 허용목록(패키지 참조·버전·안전한 속성·허용 SDK·잠금 파일, NuGet.config 는 파일 전체의 요소 구조가 packageSources·packageSourceMapping·disabledPackageSources 안의 add·clear·package 뿐, main 에서 온 줄)뿐일 때만 바로 돌리고, 그 밖(Target·Exec·Import·CustomBefore… 속성 등)이나 추적 안 된 MSBuild 입력(*.user·props/targets·*.rsp, 지난 성공 뒤 바뀐 obj/<프로젝트>.nuget.g.*)이 있으면 `mookko restore-allow <역할>`로 사람이 허락해야 합니다(허락은 그 줄 원문·파일 해시에 묶임 — 설명이 같아도 줄이 바뀌면 다시 확인, 실패해도 유지). 같은 서명의 허락은 팀 공용 기록에도 남아 다른 역할(보기 역할 QA·인수 포함)도 통과하고, 같은 서명의 확인 알림은 하나입니다(P0R3-M19). 감시 경로는 대소문자를 가리지 않고(`Directory.Build.Props`·`X.CSPROJ`, P0R3-M18), 지난 성공 기록이 있는데 기록에 없는 새 obj/*.nuget.g.* 도 확인 대상입니다(P0R3-L17). NuGet 폴더가 바뀌었거나 지난 성공 때 받은 패키지가 사라지면 다시 restore 합니다. 역할별 low 폴더는 용량에 들어가고 정리 종류 `low` 로 비울 수 있습니다.
- **강제 중지:** `mookko kill`·화면 긴급 길은 runner.json 의 시작 시각이 지금 그 pid 와 같을 때만 끝냅니다(Python 이 있으면 사람 확인을 거침). `mookko.cmd` 는 Python 이 없거나 Python 길이 실패하면(사람 확인 거부(종료 2)는 제외, 프로그램을 `MOOKKO_PIN_PROGRAM`·`MOOKKO_HOME` 으로 고정해 둔 때도 제외) `kill` 은 그 pid 명령줄이 `-m mookko _run <그 역할>` 로 끝나고 시작 시각이 같을 때만 끝내고(taskkill 종료 코드 확인), `resume` 은 PAUSED 파일만 지웁니다. 값은 환경 변수로만 넘기고, 역할 ID 는 `MOOKKO_ROLEARG` 변수 하나만·boot 와 같은 형식·길이(각 부분 1+{0,40}자)일 때만 받습니다.
- **알림:** Windows 알림(토스트·풍선·알림 센터)은 쓰지 않습니다(2026-10-15 사용자 결정). 알림은 제어 문자를 지우고 길이를 줄여 `runtime/notifications.jsonl`에 한 줄로만 남깁니다.


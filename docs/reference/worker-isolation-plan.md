# 워커 격리 계획 (2026-10-19)

보안 점검(`review/2026-10-19-mookko-product-review.md`)과 MooKKoDev 자체 점검에서 나온 치명 3건의 근본 원인은 하나다. **WSL 워커(AI 세션)가 Windows 사용자와 같은 권한으로 돈다.** 그래서 워커는 (1) Windows 자격 증명으로 제품 저장소에 push할 수 있었고, (2) `/mnt/c`로 허브·매니저 토큰과 계정 인증 파일을 읽고 interop(`*.exe` 실행)으로 화면·허브·매니저 API에 닿으며, (3) OpenRig 큐에 다른 좌석 이름으로 글을 쓸 수 있다.

같은 Windows 사용자 안에서는 ACL·DPAPI·별도 Linux uid 어느 것도 경계가 되지 않는다. DrvFs(`/mnt/c`)는 WSL의 모든 Linux 사용자에게 같은 Windows 권한으로 열리고, interop은 어느 Linux 사용자가 실행해도 Windows 사용자로 돈다. 경계는 **interop과 자동 마운트가 없는 워커 전용 실행 환경** 하나뿐이다.

## 단계

### 1단계 — 끝남 (10-19)
- 공용 bare 저장소에서 Windows Git Credential Manager를 뺐다(`credential.helper ""`, `remote.origin.pushurl no_push`). 워커 작업 사본에서 `git credential fill`이 비밀번호를 돌려주지 않고 `git push`는 `no_push`로 실패한다. 제품 main과 담당 브랜치 모두 GitHub로는 MooKKoDev가 push하지 않는다(10-19 확인: GitHub에 `openrig/*` 브랜치 0개, bare에 원격 추적 refs 0개 — 애초에 파이프라인은 GitHub push에 기대지 않았다).
- 사용자 일감 원장: 화면이 만든 `user@mookko-console` 일감만 원장(HMAC)에 적고, 원장에 없는 `user@` 일감은 화면에 "출처 확인 안 됨"으로 표시한다. PM·점검 담당의 제어 메시지는 OpenRig가 기록한 `identityProvenance`가 `transport:v1`(rig CLI가 좌석 환경에서 찍은 머리글)일 때만 받는다. 본문에 좌석 이름만 적은 `claimed:v1` 메시지는 거부한다.
- 한계: interop이 열려 있는 동안 워커는 Windows `curl.exe`로 머리글을 꾸며 보낼 수 있고, `/mnt/c`의 원장·비밀 파일을 읽을 수 있다. 1단계는 "쉬운 사칭"만 막는다.

### 2단계 — 끝남 (10-19 10:48, 끊김 약 5분)
- 도구는 HTTP 대신 **파일 mailbox**로 옮겼다(`openrig_bridge/tool_mailbox.py`). WSL→Windows 수신은 Hyper-V 방화벽이 막고 규칙 추가는 관리자 권한이라 포트를 쓰지 않는다. `mookko-skills`·`mookko-validate`·`mookko-references`와 업데이트 확인(admission)이 모두 mailbox를 거치고, finish 영수증에는 브리지 서명이 붙는다.
- 브리지 쪽 /mnt/c 의존(rules_sync의 제품 main fetch)은 Windows git bundle로 바꿨다.
- `tools/provision-worker-distro.py`로 Ubuntu를 tar로 흘려 `MooKKo-Workers`를 만들고(286초, vhdx 24GB, candidate-checks 167GB 제외), `/etc/wsl.conf`에 interop·automount 끔. 전환은 `%USERPROFILE%\MooKKoOpenRig\worker-cutover.py`(배분 멈춤 → 세션 종료 대기 → 옛 배포판 끄기 → state·workspaces 등 복사 → config.json distribution 변경 → 화면 재시작 → 배분 풀기).
- 실측(새 배포판 워커 작업 사본): `/mnt/c` 마운트 아님(0개), `cmd.exe` 실행 차단, 127.0.0.1:5288/5280/5290 도달 불가, `git credential fill` 빈 값, `git push` → no_push, `hub.json` 읽기 불가, mailbox ping·admission 응답, 전환 2분 뒤 세션 8개 기동.
- 옛 `Ubuntu` 배포판은 되돌리기용으로 남겨 두었다(vhdx 226GB, 대부분 candidate-checks). 정리는 별도 작업.
- 10-19 정리: 옛 `Ubuntu`에서 candidate-checks(1073개, 168GB)와 워커 임시 폴더 `~/.cache/mookko-tmp`(33GB)를 지웠다. state·workspaces·providers 등 되돌리기에 쓰는 것은 그대로다. 새 배포판은 `openrig_bridge/candidate_checks.py`가 쓰임이 끝난 후보 사본을 자동으로 지운다. 옛 배포판을 아예 지우는 것(`wsl --unregister Ubuntu`)은 사용자가 되돌리기가 필요 없다고 확인한 뒤에 한다.

### (참고) 2단계 원래 계획
목표: 워커와 OpenRig 데몬을 `interop=false`, `automount=false`인 배포판(예: `MooKKo-Workers`)에서 돌린다. 그 안에서는 Windows 실행 파일을 띄울 수 없고 `C:`가 보이지 않는다.

워커가 지금 interop에 기대는 것과 대체 방법:

| 지금 (WSL에서 Windows python 실행) | 대체 |
|---|---|
| `mookko-skills begin/finish`(tools/native-skills.py) — 후보 사본 스냅숏·Graphify·검증 명령 | 화면 서버(Windows)가 WSL 쪽 vEthernet 주소에 "도구 서비스" HTTP를 연다. 워커는 역할별 토큰으로 `POST /tools/skills/{begin,finish}`를 부른다. 서비스는 `\\wsl.localhost` 경로로 사본을 읽고 같은 로직을 Windows에서 돈다. |
| `mookko-validate`(tools/validate-openrig.py) — Windows 전체 검증 | 같은 서비스의 `POST /tools/validate`. 결과 영수증은 서비스가 서명해 저장하고, QA 영수증에는 그 서명만 들어간다(stdout JSON 신뢰 제거). |
| `mookko-references`(discover-openrig.py) | 같은 서비스의 `GET /tools/references`. |
| Git Credential Manager | 1단계에서 제거됨. |
| `rules_sync`의 `/mnt/c/Project/MooKKo/MooKKo` fetch (브리지 쪽) | Windows git이 `\\wsl.localhost\MooKKo-Workers\...\source.git`로 push(`refs/mookko/*`만). |
| `tests/ui_checks.py`의 WSL node | 개발용이라 현재 배포판에 남긴다. |

역할별 토큰은 `publish.json`처럼 역할 폴더에 두되, 배포판 안에서 다른 역할 폴더를 못 읽게 하려면 역할마다 Linux 사용자를 나눈다(2단계에서는 선택, 3단계 필수).

순서:
1. 도구 서비스를 화면 서버에 추가하고, 현재 배포판에서 두 경로(interop·HTTP)를 모두 열어 둔 채 QA 영수증이 서비스 서명을 쓰는지 확인한다.
2. `wsl --export`로 현재 배포판을 복제해 `MooKKo-Workers`를 만들고 `/etc/wsl.conf`에 `[interop] enabled=false`, `appendWindowsPath=false`, `[automount] enabled=false`를 둔다.
3. 워커가 쉬는 때(WSL 다시 켜기 절차와 같음)에 config.json의 `distribution`을 바꾸고 화면을 다시 켠다. OpenRig 데몬·워커 세션은 새 배포판에서 뜬다.
4. 실측: 새 배포판 워커에서 `/mnt/c` 없음, `*.exe` 실행 실패, 127.0.0.1:5288/5280/5290 도달 불가, `git credential fill` 빈 값, `mookko-skills finish`가 서비스 서명 영수증을 받는 것.

### 3단계 — 좌석 신원 (OpenRig 밖에서) — **켜지 말 것: 설계 다시 (10-19 검토)**

> **상태: 활성화 막힘(`openrig_bridge/worker_isolation.py` `ACTIVATION_BLOCKED`).** 아래 설계(bd10015, Opus 4.8 구간)는
> 10-19 독립 검토에서 **켜면 모든 워커가 멈추고 보안이 지금보다 나빠지는** 결함이 확인됐다. `config.json`에서
> `workerIsolation.enabled`를 켜도 `native.py`는 무시하고 2단계로 돌며 경고만 남기고, 활성화 도구(provision `apply`,
> iptables `script`)는 거부한다. 다시 설계한 뒤 `ACTIVATION_BLOCKED`를 비운다. 스푸핑의 고가치 경로(제어·결정·보고)는
> 1단계 provenance(`transport:v1`)·원장으로 이미 막혀 있다.

#### 3단계 — 검토 결과 (10-19, 다시 설계할 때 모두 풀어야 함)
1. **sudoers 문법 오류** — 배포판 sudo는 sudo-rs 0.2.13. 인자 안 와일드카드를 거부해 `OPENRIG_URL=* node` 줄이 `visudo -c`에서 실패 → 모든 좌석 기동 실패. 값은 막고 뒤 인자는 열려면 `/usr/bin/env *`밖에 없는데 사실상 ALL. 또 sudoers를 `/etc/sudoers.d/`에 먼저 쓰고 검사해 실패해도 깨진 파일이 남는다.
2. **sudo-rs는 환경을 늘 지운다**(env_reset 끌 수 없음). shim은 `OPENRIG_URL`만 넘겨 `OPENRIG_SESSION_NAME`·`CODEX_HOME`·`CLAUDE_CONFIG_DIR`·`TMPDIR`·PATH가 사라진다 → codex(`#!/usr/bin/env node`, 배포판에 `/usr/bin/node` 없음) 127, Claude는 역할 사용자 `~/.claude`를 봐 로그인 없음, 워커 안 `rig` 못 찾음. `/home/user`가 `0750 user:user`라 rig·역할 사용자는 설치 루트에 들어가지도 못한다.
3. **프록시가 Host 머리글을 지운다**(`HOP_BY_HOP`에 host) → 데몬(Node 22 `requireHostHeader`)이 모든 요청을 400. 시험은 파이썬 가짜 데몬이라 놓쳤다.
4. **shim fail-open** — 매니페스트·좌석이 없으면 `execv(real_bin)`으로 rig 그대로 실행. `MOOKKO_SEAT_MANIFEST`를 넣는 코드가 없고 `native.py`가 PATH를 고정해 shim이 PATH에 못 들어가므로, 켜면 shim이 아예 안 돌고 워커가 전부 **rig**(데몬 포트 허용·모든 역할로 sudo 가능)로 뜬다 — 지금보다 권한이 넓다.
5. **프록시 경로 무제한** — 모든 메서드·경로를 넘겨 워커가 rig 권한 데몬의 관리 API(`/api/rigs/import`·`/api/up`·`/api/transport/send`·`/api/config/:key`·`/api/files/write`, terminal 런타임)에 닿는다 → 매니페스트에 없는 좌석(rig로 뜸)을 만들거나 남의 pane에 명령을 쳐 넣는 권한 상승.
6. **역할 사용자가 데몬 DB를 직접 쓴다** — 역할 사용자 기본 그룹이 rig이고 문서가 state를 그룹 쓰기로 둬, `state/openrig.sqlite`에 남의 좌석으로 직접 넣어 프록시·iptables를 아예 우회.
7. **iptables가 브리지 자신을 끊는다** — `! --uid-owner rig -j REJECT`. 켜도 rig로 바뀌는 건 데몬 시작뿐이라 `runtime.py`의 `rig config/auth/up/down/capture` 호출(user)과 Windows `urllib`(NAT localhost 중계)이 막혀 화면이 데몬을 못 본다.
8. 그 밖: 배포판에 iptables 미설치, iptables `script`가 apply·revert를 한 출력에 섞어 흘려 돌리면 넣자마자 지워짐(→ `--kind`로 분리, 막힘 동안 거부), unix 모드 `os.chown` EPERM, 응답을 끝까지 모아 SSE(`chatroom`·`stream` 등)가 300초 뒤 502, chunked 본문 버림.

엔진 로그인 공유는 0640(그룹 읽기 전용)이면 토큰 자체 갱신·계정 전환이 깨져 2770/0660 + 브리지 사용자 rig 그룹으로 고쳤다(0e283e0). 위 1~8은 그대로 남아 있다.

#### (참고) 원래 설계 (10-19, 위 검토로 막힘)

#### 확인한 데몬 동작 (읽기만, 수정 금지)
OpenRig 0.6.10 데몬 dist를 읽어 좌석 신원 처리를 확정했다. (경로: `…/@openrig/cli/daemon/dist`, `…/@openrig/cli/dist`)

- **머리글 이름은 `X-OpenRig-Session`**(소문자 `x-openrig-session`). `routes/require-sender-identity.js`의 `SENDER_IDENTITY_HEADER`. `transportSenderSession(c)`가 이 머리글을 `trim`·정규화해 **그대로 행위 좌석으로 쓴다**(`provenance=transport:v1`). 본문 좌석(claim)은 머리글이 있으면 무시된다("the wire decides the actor, the body never does"). 즉 이 머리글을 쓸 수 있는 자가 아무 좌석이나 사칭한다. `routes/queue.js`(add/claim), `routes/transport.js`(send), `routes/projects.js` 등 기록 라우트가 모두 이 한 곳을 쓴다.
- 함께 봐야 할 머리글: `X-OpenRig-Origin-Unknown`(두면 `origin-unknown:v1`), `X-OpenRig-Provenance`·`X-OpenRig-Relay`(포워딩 데몬 전용 — 워커가 쓰면 provenance가 내려가거나 바뀜). 프록시는 이 네 개를 모두 지우고 `X-OpenRig-Session`만 좌석으로 넣어 `transport:v1`이 되게 한다.
- **머리글은 CLI가 좌석 env에서 한 번 찍는다**: `client.js`의 `senderIdentityHeaders()`가 `OPENRIG_SESSION_NAME`(대체 `RIGGED_SESSION_NAME`)를 읽어 `X-OpenRig-Session`으로 보낸다. 보낼 데몬 주소는 `OPENRIG_URL`(대체 `RIGGED_URL`). tmux 좌석 이름 = `canonicalSessionName` = `deriveCanonicalSessionName(pod, member, rig)` (예: `work-worker@mookko-pay-backend`).
- **좌석 env는 데몬이 넣는다**: `domain/node-launcher.js`가 좌석 tmux 세션을 만들며 `OPENRIG_SESSION_NAME`을 넣고, `startup.js`의 `launchSessionEnv`(데몬이 자기 프로세스 env에서 **한 번** 만든 것 — `OPENRIG_URL: resolvedActivityHookUrl`)를 **모든 좌석에 똑같이** 편다. tmux 서버는 데몬 프로세스의 환경·사용자로 돈다.

#### 확정 설계: **B** (근거)
"OpenRig에 소켓 피어 확인 기능 요청"(설계 A)은 제3자 일정에 걸려 지금 못 막는다. 그래서 데몬 밖에서 세우는 **설계 B**로 간다. 다만 조사로 **B의 전제가 데몬 때문에 부분적으로 막힘**을 확인했고, 그래서 B를 다음과 같이 **런타임 shim으로 실현**한다.

- 막히는 지점(중요): 데몬이 **모든 워커를 자기 tmux 서버에서 자기 리눅스 사용자로** 띄우고, 워커의 `OPENRIG_URL`을 자기 env에서 **한 번** 읽어 **모두 같게** 준다. 그래서 브리지(native.py)만으로는 (1) 워커를 역할별 사용자로 돌리거나 (2) 워커마다 다른 프록시 주소를 줄 수 없다. 데몬이 좌석 env에 주는 지점(node-launcher) 밖에서 끼어들 곳은 **데몬이 pane에 치는 런타임 명령(`node`/`codex`/`claude`)** 뿐이다.
- 실현: **워커 런타임 shim**(`tools/worker-runtime-shim.py`)을 워커 PATH 앞 디렉터리에 `node`/`codex`/`claude` 이름으로 둔다. 데몬이 친 명령이 shim을 먼저 실행하면, shim은 `OPENRIG_SESSION_NAME`(좌석)으로 매니페스트에서 역할·역할 사용자·그 역할 프록시를 찾아 **`sudo -n -u <역할사용자> env OPENRIG_URL=<역할 프록시> <진짜 런타임>`**으로 권한을 낮춰 exec 한다. `OPENRIG_SESSION_NAME`이 없는(데몬 내부) 호출은 그대로 통과한다.
- 그러면 비로소: ① 역할마다 Linux 사용자(공용 그룹 `rig`), ② 데몬은 전용 사용자 `rig`로 뜨고 loopback 5289는 iptables owner-match로 `rig` uid만 — 역할 사용자의 직접 접근 차단, ③ 역할별 프록시가 `X-OpenRig-Session`을 그 역할 좌석으로 강제. 워커가 WSL 안 curl로 머리글을 꾸며도, 데몬 포트엔 못 닿고 프록시를 지나면 좌석이 덮어써진다.
- **프록시 전송은 tcp**: 워커 CLI는 `OPENRIG_URL`을 undici `fetch`로 쓴다. undici fetch는 URL로 **unix 소켓을 못 가리킨다**(client.js가 `baseUrl=OPENRIG_URL`을 그대로 fetch에 넘김). 그래서 워커가 실제로 쓰는 프록시는 **역할별 loopback tcp 포트**이고, 역할 간 격리는 **포트별 iptables owner-match**로 준다(그 역할 uid와 `rig`만 그 포트에 ACCEPT, 나머지 REJECT). unix 소켓(0600, 역할 소유) 프록시도 구현해 뒀지만(`proxyMode: "unix"`) curl 같은 fetch 아닌 호출용이고 기본은 tcp다. — 이 부분이 원 스케치("유닉스 소켓, 워커 env 주소를 소켓으로")와 다른 점이며, CLI 전송 제약 때문이다.
- 엔진 로그인(Codex·Claude, 역할 간 공유가 맞음): 소유 `rig:rig`, 디렉터리 0750·파일 0640으로 두고 모든 역할 사용자를 `rig` 그룹에 넣어 **읽기만** 공유한다(`providers/codex`, `providers/claude`). Dev↔매니저 분리는 별개로 유지.

#### 산출물 (활성화 전까지 — WSL `--shutdown` 불필요)
- `openrig_bridge/worker_isolation.py` — 순수 계산: 머리글 덮어쓰기(`rewrite_headers`), 좌석 정규화, 역할→사용자(결정적), 매니페스트, iptables owner-match 규칙, sudoers 줄. `config["workerIsolation"]`은 `settings()`가 너그럽게 정규화(기본 `enabled:false`).
- `openrig_bridge/seat_proxy.py` — 좌석별 신원 프록시(표준 라이브러리). tcp/unix 둘 다. `--manifest`로 역할마다 하나씩 띄움(데몬 시작과 함께, 또는 boot/systemd로).
- `tools/worker-runtime-shim.py` — 위 shim. 배포판 안 워커 PATH 앞에 설치.
- `tools/provision-worker-roles.py` — 그룹·데몬 사용자·역할 사용자·엔진 로그인 공유(0640/rig)·shim 설치·sudoers·프록시 디렉터리의 **명령 계획(plan)**을 registry에서 만든다. `apply`는 활성화 단계.
- `tools/worker-isolation-iptables.py` — owner-match 규칙의 apply/revert **셸 스크립트**를 매니페스트에서 만든다(멱등, 넣기 전 `-C`). 부팅 재적용은 `/etc/wsl.conf` `[boot] command`나 systemd 유닛에 건다.
- `openrig_bridge/native.py` — `workerIsolation.enabled`면 데몬을 `daemonUser`로 띄우도록 `linux()/rig()`에 `--user`를 더함(기본 꺼짐 → 2단계 동작과 바이트 동일).
- 시험: `tests/worker_isolation_test.py`(머리글·매핑·규칙·shim), `tests/seat_proxy_test.py`(가짜 데몬 앞 프록시 종단 — 꾸민 좌석이 역할 좌석으로 덮어써짐).

#### 활성화 순서 (MooKKoDev 담당 세션이 한 WSL 창에서)
1. 매니페스트 생성: `python -X utf8 tools/provision-worker-roles.py plan --manifest-out <win> ...` → 역할↔사용자↔프록시 포트가 든 매니페스트를 배포판 안(예: `/home/user/.local/share/mookko-openrig/seat-manifest.json`, `rig` 소유·0644)에 둔다.
2. provisioning: plan이 찍은 명령을 배포판 안에서 root로 돌린다(그룹·사용자·엔진 로그인 공유·shim 설치·sudoers). sudoers의 런타임은 `which`로 절대경로를 채운다.
3. 데몬 설치 루트를 `rig`가 쓰게 그룹·권한을 맞춘다(state·workspaces·providers를 `:rig` 그룹, 그룹 쓰기). 좌석 PATH 앞에 shim 디렉터리가 오게 한다(`launchSessionEnv.PATH`는 데몬 프로세스 PATH이므로, 데몬을 띄우는 쪽 PATH 앞에 shim 디렉터리를 넣는다).
4. 프록시 기동: `python3 openrig_bridge/seat_proxy.py --manifest <linux> --daemon-port 5289`를 `rig`로 띄운다(역할마다 tcp 포트). boot/systemd로 다시 서게 건다.
5. iptables: `tools/worker-isolation-iptables.py script --manifest <linux>`의 apply 스크립트를 root로 돌린다. `/etc/wsl.conf` `[boot] command`에 걸어 부팅 때 재적용.
6. config.json에 `"workerIsolation": {"enabled": true, …}`를 켜고 화면을 다시 켠다 → native.py가 데몬을 `rig`로 띄운다.
7. 실측(활성화 세션): 역할 워커에서 `curl -H 'X-OpenRig-Session: <남의 좌석>' http://127.0.0.1:5289/...` → 거부(iptables). 자기 프록시로 보낸 요청은 좌석이 자기 것으로 기록됨. 전·후 vhdx 크기·compact는 활성화 세션이 같은 창에서.

#### 되돌리기 (3단계)
- config.json `workerIsolation.enabled`를 `false`로 되돌리고 화면을 다시 켜면 데몬이 다시 `user`로 뜬다(2단계 상태).
- iptables: `worker-isolation-iptables.py script`의 revert 줄을 root로 돌린다(`-D`, 멱등). `/etc/wsl.conf`의 `[boot] command`를 지운다.
- 프록시: `seat_proxy.py` 프로세스를 끄고 boot/systemd 등록을 뺀다. shim 디렉터리를 PATH 앞에서 뺀다(또는 shim 파일을 지운다).
- 사용자·그룹·엔진 로그인 권한은 남겨도 해롭지 않다(데몬이 `user`로 돌면 그 파일들을 그대로 읽는다). 깨끗이 지우려면 `userdel`·`groupdel`·엔진 로그인 소유권 원복.

#### 활성화 전 실측 불가 항목 (활성화 세션이 꼭 볼 것)
1. **데몬 프로세스-계보 판정**: 데몬은 pane 하위 PID/명령(`native-process-lineage.js`)으로 좌석의 running/active를 본다. pane → shim → `sudo` → (역할 uid) `node`/`codex`로 uid 경계가 생기면 이 판정이 깨질 수 있다. 활성화 후 `rig ps`의 ACTIVITY가 정상인지 꼭 확인.
2. **sudo 권한 낮춤이 데몬 운영을 깨지 않는지**: 데몬(`rig`)이 역할 사용자로 `sudo -n` 가능해야 하고, 역할 사용자 홈·`CLAUDE_CONFIG_DIR`/`CODEX_HOME`(그룹 읽기)·작업 사본 쓰기 권한이 맞아야 한다. 엔진 로그인 쓰기(토큰 갱신)는 `rig`만 하므로, 갱신 흐름이 역할 사용자에서 도는지 확인(아니면 갱신만 `rig`로).
3. **tmux 서버를 `rig`로 다시 띄우는 전환**: 지금 tmux 서버는 `user`로 떠 있다. 데몬을 `rig`로 돌리려면 좌석 세션이 쉬는 때 `rig` tmux 서버로 새로 떠야 한다(2단계 전환과 같은 창).
4. **프록시·iptables 부팅 재적용**이 `/etc/wsl.conf`나 systemd로 실제로 다시 서는지.
5. 역할 수가 많을 때 프록시 tcp 포트 범위(`proxyPortBase`~)와 iptables 규칙 수가 맞는지.

## 되돌리기
- 1단계: bare 저장소 `credential.helper`·`pushurl` 설정 두 줄을 지우면 이전과 같다(GitHub push가 필요해지면 Windows 쪽 push 관문을 만든다).
- 2단계: config.json `distribution`을 원래 배포판으로 되돌리고 화면을 다시 켠다.
- 3단계: 위 "되돌리기 (3단계)" 참고.

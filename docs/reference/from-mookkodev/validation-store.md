# 검증 실행의 보관 기한 (`mookko-validate`)

2026-10-20. `mookko-validate`는 실행마다 `%USERPROFILE%\MooKKoOpenRig\validation\<id>\`를 만들고, 그 안에 Windows checkout 전체와
전달 번들을 남겼습니다. 지우는 코드가 없어 10-19에 128개, 17GB가 쌓였습니다(checkout 14.2GB, 번들 3.2GB, evidence 1MB 미만).
실행의 checkout을 다시 여는 코드는 없습니다. 영수증은 실행 기록을 복사해 두고(`skill_receipt`), 다음 검사는 정확한 SHA로 새 사본을 만듭니다.

코드: `openrig_bridge/validation_store.py`, `openrig_bridge/validate.py`. 시험: `tests/validation_store_test.py`.

## 어디에 무엇을 두나

| 것 | 위치 | 보관 |
|---|---|---|
| 작업 사본(`checkout`, `source.bundle`) | `%TEMP%\mookko-test\dev\v-<실행 id 앞 12자>\` | 통과·`staged`·`blocked-pending`이면 실행이 끝날 때 바로 지움. 실패(`failed`·`error`·`rejected`)면 원인 확인용으로 24시간(`failedKeepHours`) |
| 근거(`evidence\`: result.json, checks.log, 계획, runner TRX) | `validation\<id>\evidence\` | 30일(`evidenceDays`), 그 뒤 실행 폴더째 휴지통 |
| 실행 잠금(`run.lock`) | `validation\<id>\run.lock` | 실행 동안 OS 잠금. 프로세스가 죽으면 저절로 풀림 |

- 작업 사본은 공통 규칙의 "시험·검증 임시 파일" 자리에 둡니다. 시험이 만든 자기 임시 폴더라 휴지통을 거치지 않고 바로 지웁니다(공통 규칙의 예외).
  git이 팩 파일을 읽기 전용으로 남기므로 읽기 전용을 풀며 지웁니다(예전처럼 `ignore_errors`로 조용히 남기지 않음).
- 경로는 예전보다 12자 짧습니다(`validation\<36자 id>\checkout` 85자 → `mookko-test\dev\v-<12자>\checkout` 73자). 10-19 사본의 가장 긴 상대 경로는 158자입니다.
- 실행 결과의 `workCopy`에 작업 사본 경로와 `removed`·`kept`가 남습니다.

## 실행 중인 것은 건드리지 않는다

- 실행은 끝날 때까지 `run.lock`을 쥡니다. 정리는 잠금을 잡아 보고, 못 잡으면(살아 있음) 그 실행의 폴더와 작업 사본을 건너뜁니다.
- 허브는 `%TEMP%\mookko-test\dev\` 아래 실행 폴더를 나이로 지웁니다(하루 한 번 24시간, MooKKoDev 업데이트 성공 직후 1시간 넘은 것;
  MooKKoHub `docs/cleanup.md`). 그래서 실행은 5분마다 작업 사본의 `.alive`를 새로 쓰고(이름 바꾸기라 폴더 시각도 바뀜) 폴더 시각을 새로 고칩니다.
- 잠금 파일이 없는 10-20 이전 실행은 나이로 판단합니다: 마지막 변경 뒤 24시간(`legacyHours`)이 지나야 손댑니다.
- 잠금이 풀렸는데 결과가 `running`인 실행(프로세스가 죽은 것)은 result.json을 `abandoned`로 고칩니다.

## 정리 (화면 서버, 1시간마다 백그라운드)

`ValidationStore`가 디스패치 옆에서 1시간(`seconds`)마다 한 번 돕니다(`CandidateChecks`와 같은 방식). 결과는 화면 상태의 `validationStore`에 있습니다.

1. `%TEMP%\mookko-test\dev\v-*` 가운데 살아 있지 않고 24시간 지난 작업 사본을 바로 지웁니다. 다른 이름(시험 실행 폴더 등)은 허브 몫이라 건드리지 않습니다.
2. `validation\` 아래 실행 id 이름의 폴더만 봅니다. 이름 붙은 폴더(`postgresql-18.6-20261016`, `integration-*` 등 사람·워커가 만든 근거)는 절대 건드리지 않습니다.
3. 예전 실행에 남은 `checkout`·`source.bundle`은 24시간이 지났으면 Windows 휴지통으로 보냅니다(`trash.discard`: 카나리를 먼저 보내 휴지통 도착을 확인하고, 보낸 뒤에도 도착을 확인).
4. 30일 지난 실행 폴더와, 번들 전달 전에 실패해 비어 있는 실행 폴더는 폴더째 휴지통으로 보냅니다.
   실행 폴더 안에 `evidence`·`run.lock`·`checkout`·`source.bundle` 말고 다른 것(누가 넣은 근거)이 있으면 폴더째 지우지 않습니다.
5. 휴지통 여유는 Windows 설정(드라이브별 최대 크기 − 지금 든 크기, `trash.bin_room`)으로 재고, 2GB를 남기고 들어갈 때만 보냅니다.
   여유를 모르거나 그 드라이브가 바로 삭제로 설정돼 있으면 아무것도 보내지 않습니다. 한 번에 30개(`perPass`)까지 보내고 나머지는 다음 차례로 미룹니다.
   휴지통을 믿을 수 없으면(`TrashUnavailable`) 그 차례를 멈춥니다. 남은 개수와 크기는 `waiting`·`waitingMb`에 있습니다.

설정은 `config.json`의 `validationStore`(`failedKeepHours`, `evidenceDays`, `legacyHours`, `seconds`, `perPass`)로 바꿉니다.

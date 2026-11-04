# dev

- 여기 두는 것: 개발 도구 스크립트(빌드 자리 `build-slots.sh`·자리 잡기 `build-slot-acquire.sh`·자리 안에서 명령 하나 `with-build-slot.sh`, 메모리·디스크 관문, 시험 DB 감싸기, WSL 실행·멈춤 표지, 기계 판정 `machine.py`)
- 두지 않는 것: 그 설정(`config/dev/`), 검사(`ci/`), 실행 데이터·표지 파일(제품 본 체크아웃 `data/`)

- 하네스 카나리 `harness-canary.sh`(PM 2026-11-04): 하네스를 바꾸면 통합 담당이 공용 제품 체크아웃이 아니라 따로 둔 사본(`/tmp/mookko-test/harness-canary/…`, `git clone --shared`, GIT_*·MOOKKO_* 끊음)에서 그 판으로 check-all을 먼저 한 번 돌린다. 통과한 판만 제품 harness.lock으로 올린다. 사본은 통과하면 바로 지우고 실패하면 남긴다.
- 빌드 자리 감시 `build-slot-watch.py`(PM 2026-11-04): 자리를 기다리는 실행이 부름. 죽은 실행의 시험 컨테이너가 쥔 잠금만 풀고, 진행 기록 없이 15분이면 경보(`<자리 폴더>/watch.log`).

---
name: mookko-rust
description: MooKKo Rust 코딩 규약. crates/ 아래 Rust 코드를 쓰거나 고치거나 리뷰할 때 반드시 먼저 읽는다 — 공용 엔진·서비스·어댑터·실행 파일 모두. 멀티스레드 극한 성능, 패닉 없는 안정성, 포트·어댑터 모듈화, 재사용, JSON 설정 주소 규칙.
---

# MooKKo Rust 규약 (요약)

정본은 `docs/policy/conventions/rust.md`(규칙 번호 R-*). 이 요약과 다르면 정본이 맞다. 어기면 하네스 CI가 커밋을 반영하지 않는다.

## 쓰기 전에
- 서비스면 엔진 포트만 쓴다. HTTP·DB·gRPC·캐시 라이브러리(axum·reqwest·sqlx·tonic·redis…)를 직접 넣지 않는다. 엔진에 없으면 바탕 담당에게 요청(R-MOD-1).
- 바깥 시스템을 붙이면 포트(trait) + 어댑터 crate + 적합성 시험(R-MOD-2).
- 포트·주소·URL은 JSON 설정에서만, 시험은 `tests/fixtures/*.json`에서만(R-CFG-1).

## 꼭 지킬 것
- 패닉 금지: `unwrap`·`expect`·`panic!`(시험 제외), 인덱스 `v[i]` 대신 `get`, `as` 대신 `TryFrom`, 정수는 `checked_*`(돈은 반드시), 부동소수점 금지(R-SAFE-*).
- 비동기: `std::thread::sleep`·`std::fs`·`block_on` 금지, 큐는 상한(무제한 채널 금지), 잠금 쥔 채 `.await` 금지, `tokio::spawn`은 `JoinSet` 안에서, 모든 바깥 호출에 기한(R-ASYNC-*).
- 속도: 공유 상태는 키별로 나눠 소유 작업 하나가 처리(잠금 대신), 빌리기·`Arc::clone`·`Bytes`, 쓸데없는 `clone`·`collect` 금지, 경계만 `dyn` 안쪽은 제네릭, 모아서 한 번에(R-PERF-*).
- 모듈: 공개 항목은 `///` 문서, 기본 비공개, 도메인 값은 newtype, 함수 80줄 이하, `use x::*` 금지(R-MOD-*).
- 로그는 `tracing`만, `println!` 금지, 비밀값 가리기(R-OBS-1).
- Call-Tree: 주요 업무 함수에 `#[tracing::instrument(skip_all, fields(...))]`, 개인정보·비밀값은 필드에 넣지 않음. HTTP·gRPC·DB 구간은 엔진이 자동 계측(R-OBS-2).
- 오류는 `thiserror` 열거형, 바깥 응답은 `EngineFault`/Problem(R-SAFE-5).
- 이름은 Rust API Guidelines, crate는 `mookko-*`(rust 금지).

## 규칙 끄기
`#[allow]`·`#[expect]`·`cfg_attr(…allow)` 금지. 시험 파일 머리의 `#![allow(clippy::unwrap_used, clippy::expect_used)]`만 허용. 그 밖은 `docs/policy/lint-exceptions.json` 등록 뒤에만(R §9).

## 끝내기 전에 (Linux, WSL `MooKKo-Linux`)
```
CARGO_TARGET_DIR=$HOME/target/mookko scripts/ci/check-all.sh
```
fmt·clippy(-D warnings)·test·deny·audit·forbid-unsafe·경계·주소·스택·규칙 끄기 검사가 모두 통과해야 끝이다. Windows 결과는 세지 않는다. 결과(명령·종료 코드·시험 수)를 보고에 적는다.

# Rust 규약

대상: `crates/` 모든 Rust 코드. 목표 순서: 안정성 → 속도 → 모듈화 → 재사용(`README.md`). 강제 표시는 `README.md` › 강제 표시.

## 1. 안전·오류 (안정성)

- R-SAFE-1 모든 crate 루트(lib·bin·test·bench·example·build script)에 `#![forbid(unsafe_code)]`. **[lint]** **[검사]** `check-forbid-unsafe.py`
- R-SAFE-2 패닉으로 오류를 처리하지 않는다: `unwrap`·`expect`·`panic!`·`todo!`·`unimplemented!`·`unreachable!`(증명된 곳 제외)·`dbg!` 금지. 시험 코드만 `unwrap`·`expect` 허용. **[lint]**
- R-SAFE-3 패닉하는 연산 금지: 배열·슬라이스 인덱스(`v[i]`, `&s[a..b]`)는 `get`·`split_at_checked`·반복자로, 문자열 바이트 자르기 금지. **[lint]** `indexing_slicing`, `string_slice`
- R-SAFE-4 정수: 넘침은 `checked_*`(돈·수량은 반드시)·`saturating_*`. `as` 형변환 금지 → `From`·`TryFrom`. 부동소수점 산술 금지(돈은 정수 최소 단위). **[lint]** `arithmetic_side_effects`, `as_conversions`, `cast_*`, `float_arithmetic`
- R-SAFE-5 오류 타입: 라이브러리는 `thiserror` 열거형, 실행 파일 경계에서만 묶는다. 오류에 비밀값·개인정보·원문 SQL을 넣지 않는다. 바깥 응답은 `EngineFault`/Problem만. **[QA]**
- R-SAFE-6 `std::process::exit`, `mem::forget` 금지(정상 종료와 Drop을 건너뜀). **[lint]** `exit`, `mem_forget`

## 2. 비동기·멀티스레드 (속도 + 안정성)

- R-ASYNC-1 요청 경로에서 막는 일 금지: `std::thread::sleep`, 동기 파일 I/O(`std::fs`), `block_on`, `block_in_place`. CPU를 오래 쓰는 일은 상한(세마포어)을 둔 `spawn_blocking`으로. **[lint]** `clippy.toml` disallowed-methods
- R-ASYNC-2 모든 큐는 상한: 무제한 채널(`unbounded_channel`, `std::sync::mpsc::channel`) 금지. 넘치면 기다리지 말고 거절(503)하거나 오래된 것부터 버리고 버린 수를 센다. **[lint]** disallowed-methods
- R-ASYNC-3 잠금을 쥔 채 `.await` 금지. 짧은 동기 구간은 `std`/`parking_lot` 잠금, `.await`를 넘겨야 하면 설계를 바꾼다(채널·소유 작업). **[lint]** `await_holding_lock`, `await_holding_refcell_ref`
- R-ASYNC-4 **잠금 대신 나눠 갖기**: 공유 상태는 키(계좌·사용자·파티션)별로 나누고, 각 조각은 담당 작업 하나가 순서대로 처리한다(엔진 원장 처리기 방식). 전역 `Mutex<HashMap>`는 뜨거운 경로에 두지 않는다. 카운터는 원자 연산(`Ordering`을 최소로, 이유를 주석). **[QA]**
- R-ASYNC-5 떠도는 작업 금지: `tokio::spawn`은 `JoinSet`·감독 구조 안에서만, 끝을 기다리거나 취소를 처리한다. 끌 때 진행 중 일을 정리한다. **[QA]**
- R-ASYNC-6 취소 안전: `select!`에는 취소돼도 상태가 깨지지 않는 future만. 아니면 주석으로 이유와 보호 방법을 적는다. **[QA]**
- R-ASYNC-7 모든 바깥 호출에 기한(timeout)·재시도 상한·지연(지터)·차단기. 기한 없는 대기 금지. **[QA]**
- R-ASYNC-8 큰 future를 스택에 두지 않는다(`Box::pin`). 쓸데없는 `async fn` 금지. **[lint]** `large_futures`, `unused_async`

## 3. 성능 (속도)

- R-PERF-1 복사 줄이기: 빌릴 수 있으면 빌린다(`&str`·`&[T]` 인자), 큰 값 공유는 `Arc`(복제는 `Arc::clone`), 바이트는 `Bytes`, 쓸데없는 `clone`·`collect`·`to_string` 금지. **[lint]** `redundant_clone`, `needless_collect`, `implicit_clone`, `clone_on_ref_ptr`, `inefficient_to_string`, `needless_pass_by_value`
- R-PERF-2 뜨거운 경로에서 할당 줄이기: `with_capacity`, 버퍼 재사용, 필요하면 `SmallVec`(잰 뒤). **[QA]** **[벤치]**
- R-PERF-3 왕복 줄이기: DB 커밋·로그·메시지는 모아서 한 번에(묶음 커밋). N+1 조회 금지. **[QA]**
- R-PERF-4 디스패치: 설정으로 고르는 바깥 경계(포트)만 `Arc<dyn Trait>`. 뜨거운 안쪽 반복은 제네릭(정적 디스패치). **[QA]**
- R-PERF-5 엔진의 뜨거운 경로마다 criterion 벤치마크, 서비스 실행 파일마다 부하 시험(초당 처리량·p50·p99·메모리). 기준보다 나빠지면 실패. 최적화는 전후 숫자를 커밋 본문에. **[벤치]**
- R-PERF-6 `clippy::perf` 전부 실패 처리. **[lint]**

## 4. 모듈화·재사용

- R-MOD-1 서비스 crate는 엔진 포트만 쓴다. HTTP·DB·gRPC·캐시 라이브러리 직접 의존 금지, 어댑터·실행 파일 의존 금지, 서비스끼리 의존 금지. **[검사]** `check-boundaries.py`, `check-stack.py`
- R-MOD-2 바깥 시스템은 포트(trait) + 어댑터 crate + 적합성 시험(`mookko-ports-conformance`)으로만. 어댑터마다 적합성 시험 파일이 있어야 한다. **[검사]** `check-boundaries.py` **[QA]**
- R-MOD-3 crate 하나에 한 가지 일. 파일 하나 600줄(파일 안 `#[cfg(test)]` 모듈은 빼고 셈), 함수 하나 80줄을 넘기면 나눈다. **[lint]** `too_many_lines` **[검사]** `check-file-size.py`(이미 넘은 파일은 `waivers.json`의 기한 있는 R-MOD-3 항목만) **[QA]**
- R-MOD-4 도메인 값은 newtype(금액·ID·키·이메일)으로, 만들 때 검증한다(parse, don't validate). 맨 `String`·`i64`를 도메인 경계에 흘리지 않는다. **[QA]**
- R-MOD-5 공개 API는 최소: 기본은 비공개, 꼭 필요한 것만 `pub`. 공개 항목은 모두 `///` 문서. 엔진 공개 API 변경은 `cargo public-api` 기록과 `cargo-semver-checks`. **[lint]** `missing_docs`, `unreachable_pub` **[검사]**(엔진 API 고정 — 엔진 담당이 도입)
- R-MOD-6 반복되는 패턴(원장 처리, 작업 처리, 재시도, 적합성 시험)은 엔진에 제네릭으로 한 번만. 서비스는 업무 규칙 trait만 구현한다. **[QA]**
- R-MOD-7 와일드카드 import 금지(`use x::*`, 시험 모듈의 `super::*` 제외). **[lint]** `wildcard_imports`

## 5. 설정·주소·관측

- R-CFG-1 포트·주소·URL은 코드·상수에 두지 않고 JSON 설정에서만. 시험은 fixtures JSON. **[검사]** `check-no-hardcoded-endpoints.py`
  - 예외는 접속 주소가 아닌 표준 식별자 URI(예: OIDC 이벤트 이름)뿐입니다. 설정으로 받으면 다른 값을 받아들이는 보안 구멍이 되므로 코드 상수로 둡니다. `docs/policy/identifier-uris.json`에 근거 표준·이유·기한(expires)·승인자(통합 담당)를 적어 등록한 정확한 글자만 빠지고, 칸이 빠지거나 기한이 지나면 검사가 실패합니다.
- R-CFG-2 설정 타입은 `deny_unknown_fields`, 주소·포트에 기본값 없음. **[QA]**
- R-OBS-1 로그는 `tracing`만(구조화 필드, 요청 ID). `println!`·`print!` 금지. 비밀값·개인정보는 로그 전에 가린다. **[lint]** `print_stdout` **[QA]**
- R-OBS-2 Call-Tree를 위해 서비스의 주요 업무 함수(공개 서비스 메서드, 원장·외부 호출을 하는 함수)에 `#[tracing::instrument]`를 붙인다. 인자는 기본으로 기록하지 않고(`skip_all`) 필요한 식별자만 `fields(...)`로, 개인정보·비밀값은 절대 넣지 않는다. HTTP·gRPC·DB·캐시·외부 호출 구간은 엔진이 자동으로 남기므로 직접 만들지 않는다. **[QA]** (`docs/spec/observability/README.md` §6)

## 6. 시험

- R-TEST-1 공개 동작마다 시험. 이름은 무엇을 보장하는지 문장으로(`rejects_overflow_and_mismatch`). **[QA]**
- R-TEST-2 시간에 의존하는 시험은 tokio 시간 멈춤(`start_paused`)으로 결정적으로. `sleep`으로 기다리는 시험은 최소로. **[QA]**
- R-TEST-3 돈·파서·변환은 속성 기반 시험(proptest). 돈·core는 돌연변이 시험(cargo-mutants)으로 시험이 잡는지 확인(엔진 시험이 자리 잡은 뒤 CI 연결). **[QA]** **[벤치]**
- R-TEST-4 바깥 시스템 시험은 실제 컨테이너(Podman)로, 주소는 시험 JSON에서. **[QA]**

## 7. 이름·서식

- R-NAME-1 Rust API Guidelines 이름 규칙(타입 `UpperCamelCase`, 함수·변수 `snake_case`, 상수 `SCREAMING_SNAKE_CASE`, 변환은 `as_`·`to_`·`into_`, 생성은 `new`·`with_`·`from_`). **[lint]**(기본 lint) **[QA]**
- R-NAME-2 crate·실행 파일 이름은 `mookko-*`, `rust` 금지. **[검사]** `check-stack.py`
- R-FMT-1 `cargo fmt`(rustfmt.toml: edition 2024, max_width 120). **[lint]** fmt 검사
- R-DOC-1 주석은 "왜"를, `///`는 "무엇·어떻게"를. 코드를 되풀이하는 주석 금지. TODO는 일감 번호와 함께. **[QA]**

## 8. 의존성

- R-DEP-1 새 crate는 필요·대안·유지 상태·`unsafe` 여부·라이선스를 `docs/architecture/engine.md` 의존 표나 커밋 본문에. crates.io만, git 의존성 금지. **[deny]** **[QA]**
- R-DEP-2 TLS는 rustls만(`openssl`·`native-tls` 금지). **[deny]**
- R-DEP-3 표준에 있는 것은 표준으로(`std::sync::LazyLock` 대신 `lazy_static`·`once_cell`을 새로 넣지 않음). **[QA]**

## 9. 규칙 끄기

- `#[allow]`·`#[expect]`·`#![allow]`·`#[cfg_attr(…, allow)]`는 금지. 시험 파일 머리의 `#![allow(clippy::unwrap_used, clippy::expect_used)]`만 예외. 그 밖은 `docs/policy/lint-exceptions.json` 등록(이유·만료일) 뒤에만. **[검사]** `check-lint-escapes.py`

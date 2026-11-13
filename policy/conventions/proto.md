# Protobuf 규약

대상: `proto/` 모든 `.proto`. 서비스 사이 통신(gRPC)과 브라우저↔백엔드(gRPC-web), 모바일 앱이 모두 이 계약을 쓴다. 생성: prost·tonic(Rust), Connect-ES(TypeScript). C# 판 `.proto`는 참고만 하고 이 규약대로 새로 쓴다(C# 판은 나중에 삭제).

## 1. 호환성 (안정성)

- P-COMPAT-1 필드 번호를 바꾸거나 다시 쓰지 않는다. 지운 필드는 `reserved`로 번호와 이름을 막는다. **[QA]**(buf 도입 전 — `buf breaking`은 도구 설치 결정 뒤, rust-qa 11-14 DEP-2)
- P-COMPAT-2 패키지에 버전: `mookko.<서비스>.v1`. 깨지는 변경은 `v2` 새 패키지로. **[QA]**(buf 도입 전 — `buf lint`)
- P-COMPAT-3 열거형 첫 값은 `<이름>_UNSPECIFIED = 0`. **[QA]**(buf 도입 전 — `buf lint`)

## 2. 설계 (모듈화·재사용)

- P-DES-1 RPC마다 전용 요청·응답 메시지(`<Rpc>Request`·`<Rpc>Response`). 메시지를 RPC끼리 돌려 쓰지 않는다. **[QA]**(buf 도입 전 — `buf lint`)
- P-DES-2 공용 타입은 `mookko.common.v1`에 한 번만: `Money{int64 minor, string currency}`, `Problem`, `Page`, `Envelope`. 서비스가 다시 정의하지 않는다. **[QA]**
- P-DES-3 돈은 `Money`만(부동소수점 필드 금지). 시각은 `google.protobuf.Timestamp`. **[QA]**
- P-DES-4 목록 RPC는 페이지 토큰과 상한. 스트리밍은 상한·기한을 문서에. **[QA]**
- P-DES-5 자체 옵션으로 호출 허용 목록(`(mookko.method).callers`)과 필드 보안 등급(개인정보·암호화)을 적는다. 엔진 패킷 생성기가 검증 코드를 만든다. **[검사]** 엔진 패킷 생성기

## 3. 이름·서식

- P-NAME-1 메시지·서비스·RPC `PascalCase`, 필드 `snake_case`, 열거형 값 `UPPER_SNAKE_CASE`(타입 이름 접두어). **[QA]**(buf 도입 전 — `buf lint`)
- P-FMT-1 `buf format`. **[QA]**(buf 도입 전)
- P-DOC-1 모든 서비스·RPC·필드에 주석(무엇·단위·제약). **[QA]**(buf 도입 전 — `buf lint COMMENTS`)

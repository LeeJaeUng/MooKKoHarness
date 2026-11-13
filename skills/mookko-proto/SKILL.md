---
name: mookko-proto
description: MooKKo Protobuf 규약. proto/ 아래 .proto(서비스 간 gRPC, 브라우저 gRPC-web, 모바일 계약)를 쓰거나 고치거나 리뷰할 때 반드시 먼저 읽는다. 하위 호환, 버전 패키지, RPC별 요청·응답, 공용 Money·Problem, 호출 허용 목록 옵션.
---

# MooKKo Protobuf 규약 (요약)

정본은 `docs/policy/conventions/proto.md`(규칙 번호 P-*). Rust는 prost·tonic, TypeScript는 Connect-ES로 생성한다. C# 판 `.proto`는 참고만 하고 이 규약대로 새로 쓴다(C# 판은 나중에 삭제).

- 필드 번호를 바꾸거나 다시 쓰지 않는다. 지운 필드는 `reserved`(번호·이름). 깨지는 변경은 새 버전 패키지(`mookko.<서비스>.v2`)(P-COMPAT-*).
- 열거형 첫 값은 `<이름>_UNSPECIFIED = 0`.
- RPC마다 전용 `<Rpc>Request`·`<Rpc>Response`. 공용 타입(`Money{int64 minor, string currency}`·`Problem`·`Page`·`Envelope`)은 `mookko.common.v1`에서만, 다시 정의 금지. 돈에 실수 필드 금지, 시각은 `Timestamp`(P-DES-*).
- 목록은 페이지 토큰과 상한. 호출 허용 목록 `(mookko.method).callers`와 필드 보안 등급 옵션을 적는다.
- 이름: 메시지·서비스·RPC `PascalCase`, 필드 `snake_case`, 열거형 값 `UPPER_SNAKE_CASE`. 모든 서비스·RPC·필드에 주석(무엇·단위·제약). `buf format`·`buf lint`·`buf breaking`을 지킨다(buf 도입 전이라 지금은 QA가 봄, 하네스 검사 없음).

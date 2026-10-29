---
name: mookko-sql
description: MooKKo SQL 규약(PostgreSQL). DB 스키마·이관(migrations/)·쿼리를 쓰거나 고치거나 리뷰할 때 반드시 먼저 읽는다. 서비스별 DB 경계, 앞으로만 가는 이관, 돈은 bigint+통화, 덧붙이기만 하는 원장, 매개변수 바인딩.
---

# MooKKo SQL 규약 (요약)

정본은 `docs/policy/conventions/sql.md`(규칙 번호 S-*). 스키마를 바꾸기 전에 `<crate>/docs/data-model.md` 설계를 QA가 승인해야 한다(관문 DBDES-01).

- 서비스마다 자기 스키마·계정, 다른 서비스 테이블 접근 금지(연결은 gRPC). 실행 계정은 DML만(S-BND-*).
- 이관은 `V<번호>__<설명>.sql`, 앞으로만, 적용된 이관 수정 금지. 큰 테이블은 `CREATE INDEX CONCURRENTLY`, 열 추가는 단계적으로, 잠금 시간을 설계서에(S-MIG-*).
- 모든 테이블에 기본 키, 새 ID는 UUIDv7.
- 라이브 패치 동안 신구 판이 함께 돌므로 구조 변경은 넓히기 → 옮기기 → 좁히기 3단계로 배포를 나눈다. 한 배포에서 이름 바꾸기·지우기 금지(S-MIG-4).
- 돈: `bigint` 최소 단위 + `char(3)` 통화, `numeric`·실수 금지. 원장은 덧붙이기만, 멱등 키 `UNIQUE`, 분할 키(`user_id`·계좌·가맹점) 열. 돈 판단은 주 DB에서 직렬화 격리 또는 명시한 잠금(S-MONEY-*).
- 쿼리: 매개변수 바인딩만(sqlx `query!`), `SELECT *` 금지, 키 기반 페이지와 상한, 자주 쓰는 조회는 `EXPLAIN`을 설계서에, N+1 금지, 문장·잠금 기한(S-Q-*).
- 이름: `snake_case`, 테이블 복수형, `<대상>_id`, 시각 `timestamptz` + `_at`, 불리언 `is_`·`has_`.

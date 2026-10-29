# SQL 규약 (PostgreSQL)

대상: 각 crate의 `migrations/`와 Rust 코드 안의 SQL. 저장소는 PostgreSQL만(ADR-0022 이어받음). 관문 DBDES-01: 스키마를 바꾸기 전에 `<crate>/docs/data-model.md` 설계를 QA가 승인.

## 1. 경계·권한 (안정성·모듈화)

- S-BND-1 서비스마다 자기 DB(스키마)와 자기 DB 계정. 다른 서비스 테이블을 읽거나 쓰지 않는다(연결은 gRPC). **[QA]** **[검사]**(이관 파일의 다른 스키마 이름 — 저장소 어댑터 담당이 도입)
- S-BND-2 실행 계정은 DML만, DDL은 이관 계정만. 대사 서비스 계정은 읽기만. **[QA]**

## 2. 이관 (안정성)

- S-MIG-1 이관은 앞으로만, 파일 이름 `V<번호>__<설명>.sql`, 적용된 이관은 고치지 않는다(엔진 `SchemaMigrator`가 막음). 되돌리는 방법은 설계서에. **[검사]** 엔진 이관기
- S-MIG-2 큰 테이블 변경은 잠금 시간을 적고 나눠서: 색인은 `CREATE INDEX CONCURRENTLY`, 열 추가는 기본값 없이 → 채우기 → 제약. **[QA]**
- S-MIG-3 모든 테이블에 기본 키. 새 행 ID는 UUIDv7(`TimeOrderedId`). **[QA]**

## 3. 돈·원장 (안정성)

- S-MONEY-1 금액은 `bigint`(최소 단위) + `char(3)` 통화. `numeric`·`real`·`double precision` 금지. **[QA]**
- S-MONEY-2 원장은 덧붙이기만(UPDATE·DELETE 권한 없음, 트리거로도 막음), 멱등 키는 `UNIQUE`, 분할 키(`user_id`·계좌·가맹점)를 처음부터 열로. **[QA]**
- S-MONEY-3 돈을 움직이는 판단은 주 DB에서(읽기 복제본 금지), 직렬화 격리 또는 명시한 행 잠금, 경합 재시도는 엔진 상한. **[QA]**

## 4. 쿼리 (속도·안정성)

- S-Q-1 쿼리는 매개변수 바인딩만(문자열 이어 붙이기 금지). sqlx 컴파일 시점 검사(`query!`) 사용. **[lint]** sqlx **[QA]**
- S-Q-2 `SELECT *` 금지(열을 적음). 목록은 페이지(키 기반 페이지, 큰 `OFFSET` 금지)와 상한. **[QA]**
- S-Q-3 자주 쓰는 조회는 `EXPLAIN`으로 색인을 확인하고 설계서에 적는다. N+1 금지. **[QA]** **[벤치]**
- S-Q-4 모든 쿼리에 문장 기한(`statement_timeout`)과 잠금 기한. **[QA]**

## 5. 이름·서식

- S-NAME-1 테이블·열은 `snake_case`, 테이블은 복수형, 외래 키는 `<대상>_id`, 시각은 `timestamptz` + `_at`, 불리언은 `is_`·`has_`. **[QA]**
- S-FMT-1 키워드 대문자, 한 줄에 절 하나. **[QA]**

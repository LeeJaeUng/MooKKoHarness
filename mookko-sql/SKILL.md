---
name: mookko-sql
description: MooKKo SQL 규약(PostgreSQL, ClickHouse 일부). DB 스키마·이관(migrations/)·쿼리·설계서(data-model.md)를 쓰거나 고치거나 리뷰할 때 반드시 먼저 읽는다. 서비스별 DB·계정, 앞으로만 가는 온라인 이관(넓히기→옮기기→좁히기, CONCURRENTLY), 돈은 bigint+통화, 덧붙이기만 하는 원장, 열마다 데이터 등급과 필드 암호화·blind index, 매개변수 바인딩.
---

# MooKKo SQL 규약 (요약)

정본은 `docs/policy/conventions/sql.md`(규칙 번호 S-*), 왜 그런지는 `docs/architecture/database.md`. 스키마를 바꾸기 전에 `<crate>/docs/data-model.md`를 먼저 고친다(DBDES-01, 지금 QA 승인은 보류지만 설계서는 지킨다). 커밋 전에 `scripts/ci/db/check-db.sh`(check-all에 포함)가 이관·설계서를 검사한다.

## 이관 파일을 쓸 때

- 위치·이름: `<crate>/migrations/NNNN_<snake 설명>.sql`(파일 이름 = 엔진 이관 ID), 0001부터 빠짐없이. 적용된 파일은 고치지 않는다. 스키마는 쓰지 않거나 `__SCHEMA__.테이블`(S-MIG-1). 이관은 이관 계정(`<서비스>_migrate`)으로만, 앱 계정으로 돌리지 않는다(S-BND-2).
- 머리 첫 줄들: `-- mookko:phase expand|migrate|contract`(필수), `CONCURRENTLY`를 쓰면 `-- mookko:transaction off` + 문장 하나 + `IF NOT EXISTS`(S-MIG-4·6). 스키마가 경로(`crates/services/<서비스>/`)로 정해지지 않으면 `-- mookko:schema <이름>`.
- 기존 테이블을 바꾸면 맨 앞 `SET LOCAL lock_timeout = '3s';`(S-MIG-5).
- 기존 테이블에 금지(S-MIG-2): 일반 `CREATE/DROP INDEX`·`REINDEX`(→ `CONCURRENTLY`), 휘발 기본값·`STORED`·`serial` 열 추가, 상수 기본값 없는 `NOT NULL` 열 추가, `ALTER COLUMN TYPE`, 검사 제약 확인 없는 `SET NOT NULL`, `NOT VALID` 없는 외래 키·검사 제약, `USING INDEX` 없는 PK·UNIQUE 추가, `TRUNCATE`·`VACUUM FULL`·`CLUSTER`·`LOCK TABLE`, `CONCURRENTLY` 없는 `DETACH PARTITION`, `UPDATE`·`DELETE`(→ 배경 이관 작업).
- 테이블·열·보기·함수 `RENAME` 금지(색인·제약 이름은 허용), `DROP COLUMN/TABLE`은 `contract` 파일에서만, `contract`에 `CREATE TABLE`·`ADD COLUMN`을 섞지 않음(S-MIG-4). 신구 판이 함께 돌므로 배포를 나눈다.
- 모든 테이블에 기본 키, 새 ID는 UUIDv7(S-MIG-3). 파티션 표의 기본 키·UNIQUE에는 파티션 열을 넣고(S-PART-1), 기본(`DEFAULT`) 파티션은 두지 않는다(S-PART-2).
- 형식: `timestamptz`(맨 `timestamp` 금지), `text` + `CHECK`(`varchar` 금지, 통화 `char(3)`만), `jsonb`, enum 금지 → `text` + `CHECK IN`, `serial` 금지 → identity·UUIDv7, 이름 63바이트 이하 snake_case(S-TYPE-*).
- 돈: `bigint` 최소 단위 + `char(3)` 통화, `numeric`·실수·`money` 금지(S-MONEY-1). `ledger`·`journal`·`audit` 테이블은 같은 파일에 `BEFORE UPDATE OR DELETE`·`BEFORE TRUNCATE` 막기 트리거, 앱 계정엔 `INSERT`·`SELECT`만(S-MONEY-2). 돈 판단은 주 DB에서 직렬화 또는 명시 잠금, 두 분할 키에 걸치면 outbox + 멱등(2PC 금지)(S-MONEY-3).
- 경계: 자기 스키마·`pg_catalog`만, `dblink`·`fdw` 금지, `CREATE ROLE/EXTENSION/DATABASE`·`ALTER SYSTEM` 금지, `GRANT`는 자기 서비스 계정에게만(`PUBLIC`·`ALL` 금지), `SECURITY DEFINER`엔 `SET search_path`(S-BND-*). DB 안 암호화(`pgcrypto`) 금지(S-SEC-7).

## 설계서를 쓸 때 (S-SEC-*, sql.md §11 형식)

- 테이블마다 `### \`이름\`` 제목 + 열 표(`열`·`형식`·`등급`·`보호` 칸) + `보관:` 문장.
- 등급: `공개`·`내부`(가명 UUID 포함)·`개인`(이름·이메일·전화·주소·IP 원문·자유 글)·`민감`(주민번호 등 고유식별정보·계좌·카드·본인 확인·건강·정확한 위치)·`비밀`(비밀번호·토큰·키·TOTP·복구 코드). 애매하면 높게.
- 보호: `개인` → `암호`(엔진 `FieldCipher`)·`암호+색인`·`해시`, `민감` → `암호`·`암호+색인`·`토큰화`, `비밀` → `해시`(비밀번호 Argon2id, 토큰 HMAC)·`암호`(되찾아야 하는 것만)·`참조`(KMS). 카드번호는 저장하지 않음(토큰화).
- 같은 값 찾기·유일이 필요하면 `암호+색인` + `<열>_bidx bytea`(HMAC-SHA-256, 열마다 다른 키, 정규화 뒤). 값 종류가 적은 열엔 blind index 금지.
- `개인` 이상 값과 SQL 바인딩 값은 로그·추적·지표·오류에 넣지 않는다(S-SEC-5).

## 쿼리를 쓸 때 (S-Q-*)

- 매개변수 바인딩만(sqlx `query!`, 식별자는 엔진 `SqlName`), `SELECT *`·`t.*` 금지, 키 기반 페이지와 상한, 자주 쓰는 조회는 `EXPLAIN`을 설계서에, N+1 금지, 외래 키 열에 색인.
- 트랜잭션은 짧게, 안에서 다른 서비스를 부르지 않고, 여러 행 잠금은 같은 키 순서로.
- 늦어도 되는 읽기만 `read`(복제본), 내가 방금 쓴 것과 돈 판단은 `write`.

## ClickHouse (§10)

로그·추적·지표만(사용자 결정 2026-10-29), 지워지면 안 되는 기록은 PostgreSQL. 대응표는 sql.md §10.1.
- TTL 필수 + `materialize_ttl_after_modify = 0`, 등급마다 기한이 다르면 등급 열 + `TTL … WHERE` 또는 DB 분리(S-CH-1).
- 변이·`MATERIALIZE …`·`OPTIMIZE … FINAL` 금지, 지우기는 TTL·`DROP PARTITION`(S-CH-2).
- 이름은 `db.표` 또는 `__DB__.표`(S-CH-4). 복제 아닌 MergeTree는 `non_replicated_deduplication_window` + 넣는 프로필 `deduplicate_blocks_in_dependent_materialized_views = 1` + 묶음 토큰(S-CH-5).
- 조회 프로필은 `readonly = 1`, `= 2`면 상한을 `MAX`·`CONST`로(S-CH-6).
- 모든 DDL은 `IF [NOT] EXISTS`(트랜잭션 DDL 없음, S-CH-7). `SELECT *` 금지, 매개변수 `{name:Type}`만, 정렬 키·파티션 키 바꾸기는 세 배포(S-MIG-4).

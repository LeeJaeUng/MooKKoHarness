---
name: mookko-sql
description: MooKKo SQL 규약(PostgreSQL, ClickHouse 일부). DB 스키마·이관(migrations/)·쿼리·설계서(data-model.md)를 쓰거나 고치거나 리뷰할 때 반드시 먼저 읽는다. 서비스별 DB·계정, 앞으로만 가는 온라인 이관(넓히기→옮기기→좁히기, CONCURRENTLY), 돈은 bigint+통화, 덧붙이기만 하는 원장, 열마다 데이터 등급과 필드 암호화·blind index, 매개변수 바인딩.
---

# MooKKo SQL 규약 (요약)

정본은 `docs/policy/conventions/sql.md`(규칙 번호 S-*), 왜 그런지는 `docs/architecture/database.md`. 스키마를 바꾸기 전에 `<crate>/docs/data-model.md`를 먼저 고친다(DBDES-01, 지금 QA 승인은 보류지만 설계서는 지킨다). 커밋 전에 `scripts/ci/db/check-db.sh`(check-all에 포함)가 이관·설계서를 검사한다.

## 이관 파일을 쓸 때

- 위치·이름: `<crate>/migrations/NNNN_<snake 설명>.sql`(파일 이름 = 엔진 이관 ID), 0001부터 빠짐없이. 출시된 서비스(`scripts/ci/db/migration-lock.json`에 잠김)의 이관은 고치지 않는다. 이미 커밋한 이관은 출시 전이라도 지금은 다시 쓸 수 없다(검사가 실패, 출시 전 예외는 사용자 결정 대기) — 새 이관 파일을 더한다. 스키마는 쓰지 않거나 `__SCHEMA__.테이블`(S-MIG-1). 이관은 이관 단계(`mookko-app migrate`, 이관 계정 `<서비스>_migrate`)에서만 돌고, 객체 주인은 `<서비스>_owner`(이관기가 `SET LOCAL ROLE`)다. 권한은 엔진 `grant`가 맞추므로 덧붙이기만 표는 서비스 이관기에 `append_only`로 지정한다(S-BND-2).
- 머리: `-- mookko:phase expand|migrate|contract`(필수). `CONCURRENTLY` 색인 이관은 **머리(맨 앞에 이어지는 `--` 줄, 사이에 빈 줄 없이) 안에 `-- mookko:transaction off`**를 두고(phase 앞뒤 상관없음), 문장은 `CREATE [UNIQUE] INDEX CONCURRENTLY IF NOT EXISTS <이름> ON __SCHEMA__.<표>` 하나만(S-MIG-4·6). 스키마가 경로(`crates/services/<서비스>/`)로 정해지지 않으면 `-- mookko:schema <이름>`.
- 기존 테이블을 바꾸면 맨 앞 `SET LOCAL lock_timeout = '3s';`(S-MIG-5).
- 기존 테이블에 금지(S-MIG-2): 일반 `CREATE/DROP INDEX`·`REINDEX`(→ `CONCURRENTLY`), 휘발 기본값·`STORED`·`serial` 열 추가, 상수 기본값 없는 `NOT NULL` 열 추가, `ALTER COLUMN TYPE`, 검사 제약 확인 없는 `SET NOT NULL`, `NOT VALID` 없는 외래 키·검사 제약, `USING INDEX` 없는 PK·UNIQUE 추가, 열 추가와 `UNIQUE`·`PRIMARY KEY`·`CHECK`·`REFERENCES`를 한 문장에, `TRUNCATE`·`VACUUM FULL`·`CLUSTER`·`LOCK TABLE`, `CONCURRENTLY` 없는 `DETACH PARTITION`, `UPDATE`·`DELETE`(→ 배경 이관 작업). 큰 테이블 변경은 잠금 시간·데이터 양을 설계서에.
- 이름 바꾸기 금지 — 테이블·열·보기·함수·**색인·제약** 모두(코드가 제약 이름으로 오류를 가름), `DROP COLUMN/TABLE`은 `contract` 파일에서만, `contract`에 `CREATE TABLE`·`ADD COLUMN`을 섞지 않음(S-MIG-4). 신구 판이 함께 돌므로 배포를 나눈다.
- `DO` 블록, `CREATE OR REPLACE FUNCTION|PROCEDURE|TRIGGER`, 이관 최상위 `SELECT`·`CALL`·`WITH` 금지 — 함수는 새 이름으로 만들고 옮긴다(S-MIG-9).
- 이관을 `include_str!`로 넣으면 ID = 파일 이름, 폴더 파일은 모두 목록에, transaction off 파일은 `.add()`로 넣지 않음(S-MIG-10). 덧붙이기만 표는 서비스 이관기에 `append_only`로 지정하고, 막기 트리거를 끄거나 REPLICA·ALWAYS로 바꾸지 않음(S-MONEY-2).
- 모든 테이블에 기본 키, 새 ID는 UUIDv7(S-MIG-3). 파티션 표의 기본 키·UNIQUE에는 파티션 열을 넣고(S-PART-1), 기본(`DEFAULT`) 파티션은 두지 않는다(S-PART-2). 이관은 부모만 만들고 달 파티션(`PARTITION OF`)은 쓰지 않으며, 부모는 서비스 코드가 엔진 `partitioned(PartitionedTable::monthly("표", 키).keep_days(n))`로 적는다 — 만들기·떼기는 엔진 유지보수 단계(S-PART-3).
- 형식: `timestamptz`(맨 `timestamp` 금지), `text` + `CHECK`(`varchar` 금지, 통화 `char(3)`만), `jsonb`, enum 금지 → `text` + `CHECK IN`, `serial` 금지 → identity·UUIDv7, 이름 63바이트 이하 snake_case(S-TYPE-*).
- 돈: `bigint` 최소 단위 + `char(3)` 통화, `numeric`·실수·`money` 금지(S-MONEY-1). `ledger`·`journal`·`audit` 테이블은 같은 파일에 `BEFORE UPDATE OR DELETE`·`BEFORE TRUNCATE` 막기 트리거, 앱 계정엔 `INSERT`·`SELECT`만, 멱등 키는 `UNIQUE`(파티션 표면 파티션 열과 함께), 분할 키(`user_id`·계좌·가맹점)를 처음부터 열로(S-MONEY-2). 사슬·구간 머리(`…_head(s)`, 분할 키당 한 행)는 지금 상태 표라 제외. 돈 판단은 주 DB에서 직렬화 또는 명시 잠금, 두 분할 키에 걸치면 outbox + 멱등(2PC 금지)(S-MONEY-3).
- 같은 배포 VALIDATE(S-MIG-4 예외): 바로 앞 넓히기가 건 NOT VALID 제약을 VALIDATE만 하는 파일은 머리 `-- mookko:validate-deploy same <이유>|next`(또는 설계서 이관 표 줄). 기한 안에 못 끝나면 다음 배포로.
- 경계: 자기 스키마·`pg_catalog`만, `dblink`·`fdw` 금지, `CREATE ROLE/EXTENSION/DATABASE`·`ALTER SYSTEM` 금지, `GRANT`는 자기 서비스 계정(`<서비스>_owner`·`_migrate`·`_app`·`_ro`·`_recon`·`_maint`(예약)·`_audit_reader`)에게만(`PUBLIC`·`ALL` 금지), `SECURITY DEFINER`엔 `SET search_path`, 스키마·DB `CREATE` 권한을 주지 않음(S-BND-*). DB 안 암호화(`pgcrypto`) 금지(S-SEC-7).

## 이름 (S-NAME-1)

테이블·열은 `snake_case`, 테이블은 복수형, 외래 키 `<대상>_id`, 시각 `timestamptz` + `_at`, 불리언 `is_`·`has_`, blind index `<열>_bidx`·`<열>_bidx_kid`.

## 설계서를 쓸 때 (S-SEC-*, sql.md §11 형식)

- 테이블마다 `### \`이름\`` 제목(서비스가 이름을 정하면 `<원장>_heads`처럼 꺾쇠) + 열 표(`열`·`형식`·`등급`·`보호` 칸) + `보관:` 문장. 검사가 이관이 만드는 열(ADD COLUMN 포함)과 대조하므로 열을 빠뜨리지 않는다.
- 등급: `공개`·`내부`(가명 UUID 포함)·`개인`(이름·이메일·전화·주소·IP 원문·자유 글)·`민감`(주민번호 등 고유식별정보·계좌·카드·본인 확인·건강·정확한 위치)·`비밀`(비밀번호·토큰·키·TOTP·복구 코드). 애매하면 높게.
- 보호: `개인` → `암호`(엔진 `FieldCipher`)·`암호+색인`·`해시`, `민감` → `암호`·`암호+색인`·`토큰화`, `비밀` → `해시`(비밀번호 Argon2id, 토큰 HMAC)·`암호`(되찾아야 하는 것만)·`참조`(KMS). 카드번호는 저장하지 않음(토큰화).
- 같은 값 찾기·유일이 필요하면 `암호+색인` + 엔진 `BlindIndex::compute("서비스/테이블/열", &Normalized::email|phone(..)?)`의 값을 `<열>_bidx bytea`(32바이트 CHECK, UNIQUE 또는 색인)와 `<열>_bidx_kid text`(키 ID, `CHECK (… ~ '^[A-Za-z0-9_-]{1,32}$')`, 같이 차거나 같이 빔)에. 값 종류가 적은 열엔 blind index 금지. 키 교체 중 찾기는 모든 키 값으로 `= ANY`, 유일 확인은 advisory 잠금(database.md §9.3).
- `개인` 이상 값과 SQL 바인딩 값은 로그·추적·지표·오류에 넣지 않는다(S-SEC-5).
- 읽기 계정 기본은 닫힘: 여는 것은 `reader_all_tables()` 또는 `const READER_TABLES`→`reader_table`. 연 표 중 `개인` 이상 열이 있는 표는 감춘다: 이관기 파일에 `const READER_HIDDEN`(표째) 또는 `const READER_COLUMNS`(`개인` 미만 열만)를 두고 같은 파일에서 `reader_hidden`·`reader_columns`로 넘긴다(S-SEC-9). 대사 계정(`_recon`, 돈 DB만)은 이관이 만든 보기(`개인` 이상 열을 쓰지 않음)만 읽고, `const RECON_VIEWS`를 `recon_view`로 넘긴다.
- 키 파기(`RowKeys`)의 감싼 키는 서비스 DB가 아니라 키 DB(`crates/services/<서비스>/keys/migrations/`, 스키마 `<서비스>_keys`, 백업 4일·Q-DB-4)의 `row_keys(subject_id, purpose, wrapped_key bytea, created_at)`에만. `dek`·`row_key`·`data_key` 같은 다른 이름으로도 서비스 DB에 두지 않고, 서비스 DB의 `bytea` key 열은 설계서 보호 `해시`(아니면 `이름 예외`). 키 DB에는 그 모양의 키 표만, 계정은 owner·migrate·app, 앱은 SELECT·INSERT·DELETE만, `wrapped_key`는 `비밀`·`암호`, 파기 기록은 서비스 DB에(S-SEC-10, database.md §9.8).

## 쿼리를 쓸 때 (S-Q-*)

- 매개변수 바인딩만(sqlx `query!`, 식별자는 엔진 `SqlName`), `SELECT *`·`t.*` 금지, 키 기반 페이지와 상한, 자주 쓰는 조회는 `EXPLAIN`을 설계서에, N+1 금지, 외래 키 열에 색인.
- 모든 접속에 문장·잠금·유휴 트랜잭션 기한(database.md §3.3, 앱 일반 5초·1초·10초)(S-Q-4).
- 트랜잭션은 짧게, 안에서 다른 서비스를 부르지 않고, 여러 행 잠금은 같은 키 순서로.
- 늦어도 되는 읽기만 `read`(복제본), 내가 방금 쓴 것과 돈 판단은 `write`.

## ClickHouse (§10)

로그·추적·지표만(사용자 결정 2026-10-29), 지워지면 안 되는 기록은 PostgreSQL. 대응표는 sql.md §10.1.
- TTL 필수 + `materialize_ttl_after_modify = 0`, 등급마다 기한이 다르면 등급 열 + `TTL … WHERE` 또는 DB 분리(S-CH-1).
- 변이·`MATERIALIZE …`·`OPTIMIZE … FINAL` 금지, 지우기는 TTL·`DROP PARTITION`(S-CH-2).
- 이름은 `db.표` 또는 `__DB__.표`(S-CH-4). 복제 아닌 MergeTree는 `non_replicated_deduplication_window` + 넣는 프로필 `deduplicate_blocks_in_dependent_materialized_views = 1` + 묶음 토큰(S-CH-5).
- 조회 프로필은 `readonly = 1`, `= 2`면 상한을 `MAX`·`CONST`로(S-CH-6).
- 모든 DDL은 `IF [NOT] EXISTS`(트랜잭션 DDL 없음, S-CH-7). `SELECT *` 금지, 매개변수 `{name:Type}`만, 정렬 키·파티션 키 바꾸기는 세 배포(S-MIG-4).

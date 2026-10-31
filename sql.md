# SQL 규약 (PostgreSQL, ClickHouse 일부)

대상: 각 crate의 `migrations/`(이관 파일), Rust 코드 안의 SQL, 설계서 `<crate>/docs/data-model.md`. 저장소는 PostgreSQL(ADR-0022 이어받음), 로그·추적·지표만 ClickHouse(§10, 사용자 결정 2026-10-29). 왜 그렇게 하는지와 운영 모양은 DB 설계 정본 [`docs/architecture/database.md`](../../architecture/database.md)입니다. 관문 DBDES-01(설계서 먼저)·SEC-01·FINOPS-01(`docs/policy/gates.md`, 지금 QA·설계 승인은 보류 — 설계서는 그대로 지킴).

강제 표시는 [README.md](README.md) › 강제 표시. 이 규약의 **[lint]**·**[검사]**는 `scripts/ci/db/check-db.sh`(check-all이 부름)입니다.

| 검사 | 하는 일 |
|---|---|
| `scripts/ci/db/migration_lint.py` | 이관 파일(`crates/**/migrations/*.sql`)과 Rust 안 SQL 문자열을 읽어 아래 [lint] 규칙을 판정 |
| `scripts/ci/db/data_classes.py` | 설계서의 열마다 등급·보호가 적혔는지, 등급에 맞는 보호인지 판정 |
| `scripts/ci/db/migration_apply.py` | 실제 PostgreSQL(시험 컨테이너)에 서비스 계정을 만들고 이관을 차례대로 적용한 뒤 목록(catalog)으로 다시 확인 |

## 1. 경계·권한

- S-BND-1 서비스마다 자기 DB·같은 이름 스키마·자기 계정. 다른 서비스 테이블을 읽거나 쓰지 않는다(연결은 gRPC). 이관 SQL의 스키마 이름은 자기 스키마·`pg_catalog`만. **[lint]** **[QA]**
- S-BND-2 계정은 `<서비스>_owner`(로그인 없음, 스키마·객체 주인)·`_migrate`(주인의 구성원, 이관 때만 — 엔진 이관기가 `SET LOCAL ROLE <서비스>_owner`로 만듦)·`_app`(테이블마다 DML만)·`_ro`(읽기만)·`_recon`(대사 보기만)·`_maint`(파티션 함수만)·`_audit_reader`(감사 읽기만, 운영툴). 이 밖의 계정은 이 목록에 먼저 더함(규약 변경 — 넓히기는 사용자 결정). 이관은 이관 단계(`mookko-app migrate`)에서만, 실행 파일은 `verify`만. 앱 계정에 DDL(스키마·DB `CREATE`)·`TRUNCATE`·`TRIGGER`·`REFERENCES` 없음, 덧붙이기만 하는 테이블에 `UPDATE`·`DELETE` 없음 — 권한은 엔진 `grant`가 맞추므로 덧붙이기만 표는 서비스 이관기에 `append_only`로 지정한다. 설계서에 계정 표를 둔다. **[lint]**(스키마 CREATE 주기) **[검사]** `migration_apply.py`(주인·앱 계정 권한) **[QA]**(`append_only` 지정)
- S-BND-3 `dblink`·`postgres_fdw`·`CREATE SERVER`·`COPY … PROGRAM`·서버 파일 `COPY` 금지. **[lint]**
- S-BND-4 서비스 이관에 `CREATE ROLE`·`ALTER ROLE`·`DROP ROLE`·`CREATE DATABASE`·`CREATE EXTENSION`·`ALTER SYSTEM` 금지(DB 준비 스크립트의 일). **[lint]**
- S-BND-5 `GRANT`는 자기 서비스 계정에게만: `<스키마>_` + S-BND-2의 접미어(`owner`·`migrate`·`app`·`ro`·`recon`·`maint`·`audit_reader`). `TO PUBLIC`·`GRANT ALL`·`WITH GRANT OPTION` 금지. **[lint]**
- S-BND-6 `SECURITY DEFINER` 함수는 `SET search_path = <스키마>, pg_catalog`를 함께 둔다(권한 올리기 방지). **[lint]**
- S-BND-7 서비스·실행 파일 코드(`crates/services/*/src`, `crates/apps/*/src`)는 DDL·권한 문장(`CREATE|ALTER|DROP TABLE·INDEX·…`, `ALTER TABLE … ATTACH|DETACH PARTITION`, `TRUNCATE`, `GRANT … ON|TO`, `REVOKE … ON|FROM`)을 쓰지 않는다. 검사는 문자열 안의 SQL 주석(`--`, `/* */`)을 지운 뒤, SQL 문장 머리(문자열 처음이나 `;` 뒤)에 오는 것만 본다(감사 동작 이름 `handle.revoke` 같은 글은 문장이 아님). 구조는 이관 파일, 파티션 유지보수는 엔진 작업(E-DB-5)이 바꾼다. 서비스 실행 경로가 구조를 바꾸면 이관 검사·적용 시험·설계서 대조를 모두 비켜 가기 때문이다. 기한 있는 예외는 `scripts/ci/db/exceptions.json`에 id·파일·이유·근거 문서(`adr`: 저장소 기준 경로와 §절, 승인 — gates.md waived의 근거 문서 + 만료일)·끝내는 조건·기한·승인자를 적는다(DB 담당이 올림, 근거 문서가 없으면 실패). 기한이 지나면 check-db가 실패한다. 지금 예외: links 파티션 유지보수(`guard.rs`)·운영툴 파티션 미리 만들기(`apps/mookko-operations/src/migrate.rs`), 둘 다 E-DB-5 통합 뒤 다음 단위까지, 기한 2026-11-30. **[lint]** `migration_lint.py`

## 2. 이관

- S-MIG-1 이관 파일은 `<crate>/migrations/NNNN_<snake 설명>.sql`(엔진 `SchemaMigrator` ID 형식 `0001_name`과 같음 — 파일 이름에서 `.sql`을 뺀 것이 이관 ID), 번호는 0001부터 빠짐없이. 앞으로만, 적용된 이관은 고치지 않는다(엔진 이관기가 SHA-256으로 막음). 되돌리는 방법은 설계서에. 스키마 이름은 쓰지 않거나(이관 계정의 `search_path`) `__SCHEMA__.테이블` 자리 표시로 쓴다(이관기가 바꿈). **[lint]**(이름·번호) **[검사]** 엔진 이관기
  - **출시 잠금**: 서비스가 출시되면 그 서비스 `migrations/` 파일의 SHA-256(엔진과 같은 계산: `__SCHEMA__`를 운영 스키마 이름으로 바꾼 뒤, 줄 끝을 LF로)을 `scripts/ci/db/migration-lock.json`에 적는다. 그 뒤로 잠긴 파일을 고치거나 지우거나 이름을 바꾸면 검사가 실패하고, 이 실패는 유예(pending.json)로 넘길 수 없다. 잠금 목록에서 항목·파일·값을 지우거나 바꿔도 git 기록 비교로 실패한다. 출시된 서비스의 새 이관은 같은 커밋에서 잠금 목록에 더한다. **[lint]** `migration_lint.py`(잠금)
  - **지금은 이미 커밋한 이관을 다시 쓸 수 없다**: 잠금 전이라도 `historyCheckedSince` 뒤 커밋이 이미 있던 이관을 바꾸거나 이름을 바꾸거나 지우면, 커밋 본문 표시와 상관없이 검사가 실패한다(작업 사본의 바꿈도). 바꿀 것은 새 이관 파일로 더한다. **[lint]** `migration_lint.py`
  - **출시 전 예외 — 사용자 결정 대기, 효력 없음**(규약 완화라 사용자 결정의 날짜·인용이 필요함, QA 7차·10차 2026-10-30. 통합 담당이 사용자께 묻는 중. 승인되면 통합 담당이 `migration-lock.json`의 `prelaunchRewrite`에 `allowed: true`와 `decidedBy`(날짜·인용)를 적고 이 줄에도 적는다. 거절되면 이 문단을 지운다). 승인되면: 잠금 전에는 이미 커밋한 이관 파일을 다시 써도 된다(파일 합치기·고치기). 조건 넷이 모두 맞아야 한다. (1) 그 이관을 적용한 DB가 지우고 다시 만들 수 있는 개발·시험 DB뿐이다. (2) 같은 커밋에서 설계서(`data-model.md`)를 함께 고친다. (3) 커밋 본문에 `출시 전 이관 다시 씀: <파일>`과 이유를 적는다. (4) 다른 담당이 그 이관 위에 쌓은 것이 없다. 기한은 그 서비스의 출시까지다. 출시란 지울 수 없는 데이터를 담는 DB(라이브, 또는 데이터를 남기는 외부 시험)가 처음 생기는 것이다. **[lint]** `migration_lint.py`(조건 (3): git 기록에서 `migration-lock.json`의 `historyCheckedSince` 뒤 커밋이 이미 있던 이관을 바꾸거나 이름을 바꾸거나 지웠으면 그 커밋 본문에 표시와 파일 이름이 있어야 함 — 기록을 못 읽으면 건너뜀(통과 아님), 하네스 CI는 `MOOKKO_REQUIRE_GIT_HISTORY=1`) **[QA]**(조건 (1)·(2)·(4))
  - **누가**: 출시 시점은 사용자가 정한다. 통합 담당이 출시 배포 전에 `python3 -X utf8 scripts/ci/db/migration_lint.py --lock <폴더> --decided-by <사용자 결정 근거> --launched-at YYYY-MM-DD`로 잠금을 남기고, 그 커밋은 DB 담당이 검토한다. 잠금을 풀거나 잠긴 값을 바꾸려면 사용자 결정이 있어야 하고, 운영 DB를 다시 만드는 경우뿐이다.
- S-MIG-2 기존 테이블에 긴 잠금·다시 쓰기를 부르는 문장 금지(같은 파일에서 만든 새 테이블은 예외). 대신 쓰는 방법은 database.md §7.2 표. 큰 테이블을 바꾸는 이관은 잠금 시간과 데이터 양을 설계서에 적는다(DBDES-01). **[lint]** **[QA]**(설계서의 잠금 시간)
  - a `CREATE INDEX`·`DROP INDEX`·`REINDEX`는 `CONCURRENTLY`로
  - b `ADD COLUMN`에 휘발 기본값(`clock_timestamp()`·`random()`·`gen_random_uuid()`·`uuidv7()`·`nextval()` 등)·`GENERATED … STORED`·`serial`·`identity` 금지(상수·`now()` 기본값은 허용 — 11+ 메타데이터만)
  - c `ADD COLUMN … NOT NULL`은 상수 기본값과 함께만
  - d `ALTER COLUMN … TYPE` 금지
  - e `SET NOT NULL`은 같은 파일 앞에서 `VALIDATE CONSTRAINT`(검사 제약 `c IS NOT NULL`)를 한 뒤에만
  - f `ADD FOREIGN KEY`·`ADD CHECK`는 `NOT VALID`로, 검증은 다음 파일의 `VALIDATE CONSTRAINT`. 열 추가와 `CHECK`·`REFERENCES`를 한 문장에 쓰지 않음
  - g `ADD PRIMARY KEY`·`ADD UNIQUE`는 `USING INDEX`(먼저 `CREATE UNIQUE INDEX CONCURRENTLY`). 열 추가와 `UNIQUE`·`PRIMARY KEY`를 한 문장에 쓰지 않음
  - h `TRUNCATE`·`VACUUM FULL`·`CLUSTER`·`LOCK TABLE`·`SET TABLESPACE`·`SET LOGGED`·`SET UNLOGGED` 금지
  - i `DETACH PARTITION`은 `CONCURRENTLY`로
  - j 파티션 부모 색인은 `ON ONLY 부모` → 파티션마다 `CONCURRENTLY` → `ATTACH PARTITION` **[QA]**
- S-MIG-3 모든 테이블에 기본 키(`PARTITION OF` 자식은 부모 것을 받음). 새 행 ID는 UUIDv7(`TimeOrderedId`). **[lint]**(기본 키) **[검사]** `migration_apply.py` **[QA]**(UUIDv7)
- S-MIG-4 라이브 패치 동안 신구 판이 함께 돈다. 구조 변경은 **넓히기 → 옮기기 → 좁히기**를 서로 다른 배포에 싣는다. 파일 머리에 `-- mookko:phase expand|migrate|contract`가 있어야 하고, 이름 바꾸기(`RENAME` — 테이블·열·보기·함수·스키마·**색인·제약** 모두, `SET SCHEMA`)는 언제나 금지(서비스·엔진 코드가 제약 이름으로 오류를 가르므로 색인·제약 이름도 바꾸면 옛 판이 깨짐 — 새 이름으로 만들고 옮긴 뒤 좁히기에서 옛것을 지움), `DROP COLUMN`·`DROP TABLE`·`DROP SCHEMA`는 `contract` 파일에서만, `contract` 파일에는 `CREATE TABLE`·`ADD COLUMN`을 함께 넣지 않는다. 배포를 나눴는지는 **[QA]**. **[lint]**(머리·이름 바꾸기·지우기·섞기) (`docs/spec/observability/README.md` §9.3)
- S-MIG-5 기존 테이블을 바꾸는 파일은 맨 앞에 `SET LOCAL lock_timeout = '…'`(5초 이하). 잠금 실패는 이관기가 지연을 두고 다시 시도한다(엔진 요청 E-DB-4). **[lint]**
- S-MIG-6 `CONCURRENTLY`는 트랜잭션 안에서 돌 수 없다. 그런 이관은 **머리(앞 빈 줄 뒤 맨 앞에 이어지는 `--` 줄, 사이에 빈 줄 없이) 안에 `-- mookko:transaction off`**를 두고(엔진 이관기가 머리 안 어디서든 읽어 트랜잭션 밖을 고름 — phase 앞이든 뒤든, 통합 결정 2026-10-31, 엔진 02f0f4a), 문장은 엔진이 받는 `CREATE [UNIQUE] INDEX CONCURRENTLY IF NOT EXISTS <이름> ON __SCHEMA__.<표>` **하나만** 둔다. `DROP INDEX`·`REINDEX`·`DETACH PARTITION`의 `CONCURRENTLY`는 엔진이 받을 때까지 쓰지 않는다. 트랜잭션 파일에는 `CONCURRENTLY`를 쓰지 않는다. **[lint]** **[검사]** `migration_apply.py`(엔진과 같은 규칙으로 적용)
- S-MIG-10 이관을 실행 파일에 넣어 쓰면(`include_str!` + `SchemaMigrator::add`) 코드의 이관 ID는 파일 이름(`.sql` 뺀 것)과 같고, 폴더의 이관 파일은 모두 한 번씩 들어 있어야 한다. `.add()`는 늘 트랜잭션 안에서 돌리므로 머리에 `-- mookko:transaction off`가 있는 파일은 엔진 `add_embedded`(머리를 보고 고름, E-DB-13)·`add_generated`(E-DB-14)·`add_concurrent_index`로 넣는다(검사는 crate가 그중 하나를 쓰면 통과로 보고, 파일별로 맞게 보내는지는 [QA] — `add_embedded`를 권함). 폴더째 읽으려면 `add_dir`. **[lint]** `migration_lint.py`
- S-MIG-11 **엔진 생성 SQL 고정 파일**: 이미 코드로 적용한 이관(예: 엔진 `SequencedStream::create_table_sql()` 출력)을 파일로 옮길 때는, 체크섬을 지키려고 엔진 출력과 글자 하나까지 같게 둔다(따옴표 친 스키마 이름만 `__SCHEMA__`로). 그런 파일은 `scripts/ci/db/engine-generated.json`에 경로·SHA-256(파일 글, 줄 끝 LF)·source·이유·기한·승인자를 적고, 서비스 이관기는 그 파일을 엔진 `SchemaMigrator::add_generated(id, 엔진 출력, 파일 글)`로 넣는다(E-DB-14: 머리를 뗀 본문이 엔진 출력과 글자로 다르면 이관기가 거부). 아직 옮기지 않은 서비스는 옛 방식 `test` 칸(파일 = 엔진 출력 비교 Rust 시험 `<경로>::<함수>`)으로도 받는다. SHA가 같을 때만 phase 머리(S-MIG-4)와 큰따옴표 이름(S-TYPE-6)을 건너뛴다. 다른 규칙은 그대로 본다. 내용이 바뀌면 예외가 없어져 보통 규칙으로 판정되고, 기한이 지나거나 칸이 빠지면 실패한다. 실행 파일에 넣어 쓰는 서비스는 이 파일을 `include_str!` 목록에 두지 않고 엔진 함수로 같은 글을 만들어 적용해도 된다(S-MIG-10 예외). 그 파일을 등록부 SHA대로 되돌리는 커밋은 S-MIG-1 다시 쓰기 금지에서 뺀다. 코드로 적용하던 이관 ID(서비스 코드에 그 ID 글자가 있던 것)를 새 파일로 바꾸는 커밋은, 그 파일이 이 등록부에 있고 그 커밋의 내용이 등록 SHA와 같아야 한다(`migration-lock.json` `codeIdCheckSince` 뒤 커밋, git 기록). 등록부는 DB 담당만 고친다. **[lint]** `migration_lint.py`(SHA, `add_generated` 호출 또는 비교 시험, 코드 ID → 파일 바꿈)
- S-MIG-7 이관 파일에서 기존 테이블의 `UPDATE`·`DELETE` 금지(채우기는 배경 이관 작업, database.md §7.1). 작은 참조 데이터 `INSERT`는 허용. **[lint]**
- S-MIG-8 이관은 CI에서 실제 PostgreSQL(운영과 같은 큰 판)에 처음부터 엔진 이관기와 같은 길(주인 역할·`search_path`·`lock_timeout`·트랜잭션 밖 판정·`grant`)로 적용해 본다. **[검사]** `migration_apply.py`
- S-MIG-9 `DO` 블록, `CREATE OR REPLACE FUNCTION|PROCEDURE|TRIGGER`, 이관 최상위의 `SELECT`·`CALL`·`WITH`·`EXECUTE`(새 이름 함수를 만들어 부르는 우회) 금지. `DO` 본문은 검사가 볼 수 없고(안의 `UPDATE`·`TRUNCATE`·`DISABLE TRIGGER`가 빠져나감), `CREATE OR REPLACE`는 막기 함수를 거부하지 않는 함수로 바꿔칠 수 있다. 함수를 바꾸려면 새 이름으로 만들고 트리거를 옮긴 뒤 좁히기에서 옛것을 지운다. **[lint]** **[검사]** `migration_apply.py`(막기 함수가 `RAISE EXCEPTION`하는지)

## 3. 형식

- S-TYPE-1 시각은 `timestamptz`만(`timestamp`·`timetz` 금지). 날짜만이면 `date`. **[lint]**
- S-TYPE-2 글자는 `text` + `CHECK (char_length(…) …)`. `varchar`·`char(n)` 금지, 예외는 통화 `char(3)`. **[lint]**
- S-TYPE-3 JSON은 `jsonb`만(`json` 금지), 크기 상한 `CHECK (octet_length(c::text) <= …)`. **[lint]**(`json`) **[QA]**(상한)
- S-TYPE-4 `CREATE TYPE … AS ENUM` 금지(값을 지울 수 없어 넓히기→좁히기가 안 됨) → `text` + `CHECK (c IN (…))`. **[lint]**
- S-TYPE-5 `serial`·`bigserial`·`smallserial` 금지 → `GENERATED ALWAYS AS IDENTITY` 또는 UUIDv7. **[lint]**
- S-TYPE-6 이름은 `snake_case` ASCII, 63바이트 이하(넘으면 PostgreSQL이 조용히 잘라 이름이 겹침), 큰따옴표 이름 금지. **[lint]**

## 4. 돈·원장

- S-MONEY-1 금액은 `bigint`(최소 단위) + `char(3)` 통화. `numeric`·`decimal`·`real`·`double precision`·`float`·`money` 형식 금지. 금액 이름 열(`amount`·`balance`·`price`·`fee`·`_minor`)은 `bigint`이고 같은 테이블에 `…currency` 열이 있다. **[lint]**
- S-MONEY-2 원장·감사·분개(이름에 `ledger`·`journal`·`audit`, 사슬·구간 머리 `…_head(s)`는 분할 키당 한 행을 고쳐 쓰는 지금 상태 표라 제외 — 이력을 그 표에 쌓으면 안 됨 [QA])는 덧붙이기만. 오래된 것을 지울 때도 `DELETE`가 아니라 파티션 떼기 또는 키 파기로: 앱 계정에 `UPDATE`·`DELETE` 권한 없음 + 같은 파일에 `BEFORE UPDATE OR DELETE`·`BEFORE TRUNCATE` 막기 트리거. 멱등 키는 `UNIQUE`, 분할 키(`user_id`·계좌·가맹점)를 처음부터 열로. 막기 트리거는 기본 `ENABLE`만(`DISABLE`·`ENABLE REPLICA`·`ENABLE ALWAYS TRIGGER`, `session_replication_role` 바꾸기 금지). 덧붙이기만 표는 서비스 이관기가 `append_only`로 지정한다(엔진 `grant`). **[lint]**(트리거, REPLICA·ALWAYS, `session_replication_role`, `append_only` 지정 — 서비스 소스에 표 이름과 `append_only`) **[검사]** `migration_apply.py`(권한, 켜진 트리거는 `tgenabled = 'O'`만, UPDATE·DELETE·TRUNCATE를 실제로 해 봄) **[QA]**(분할 키·멱등)
- S-MONEY-3 돈을 움직이는 판단은 주 DB(`write`)에서(읽기 복제본 금지), 직렬화 격리 또는 명시한 행 잠금, 경합 재시도는 엔진 상한. 두 분할 키에 걸친 일은 outbox + 멱등 키(2PC 금지). **[QA]**

## 5. 분할

- S-PART-1 시간으로 쌓이고 떼어 낼 표(원장 항목·감사·이벤트)는 월별 범위 파티션, 기본 키와 모든 UNIQUE에 파티션 열(예: `seq` 하나만 기본 키인 파티션 표는 PostgreSQL이 거부 — 멱등 키 UNIQUE도 파티션 열을 함께). **[lint]**(기본 키·UNIQUE) **[QA]**(파티션할 표 고르기)
- S-PART-2 기본(`DEFAULT`) 파티션 금지(새 파티션 붙일 때 기본 파티션을 훑으며 잠그고, 기본 파티션이 있으면 `DETACH … CONCURRENTLY`를 쓸 수 없음). 유지보수 작업이 3달 앞까지 미리 만든다(만드는 주체는 엔진 파티션 작업 E-DB-5, 설계서에 적음). **[lint]** **[검사]** `migration_apply.py`
- S-PART-3 파티션 만들기·떼기는 `<서비스>_maint`의 정해진 함수만, 지우기는 `DETACH … CONCURRENTLY` 뒤 `DROP`(`DELETE`로 지우지 않음). **[QA]**
- S-PART-4 돈 테이블은 분할 키 열을 모든 행에, 논리 버킷은 `FNV-1a(키) mod 1024`(엔진 `PartitionLeases`). 뜨거운 키는 database.md §4.3대로. **[QA]**

## 6. 데이터 보호

- S-SEC-1 설계서의 **모든 테이블의 모든 열**에 등급(`공개`·`내부`·`개인`·`민감`·`비밀`)과 보호(`평문`·`암호`·`암호+색인`·`해시`·`토큰화`·`참조`)를 적는다(형식은 §11). 애매하면 높은 등급. **[검사]** `data_classes.py`
- S-SEC-2 등급마다 쓸 수 있는 보호(database.md §9.2): `공개`·`내부` → `평문` 등 무엇이든, `개인` → `암호`·`암호+색인`·`해시`, `민감` → `암호`·`암호+색인`·`토큰화`, `비밀` → `해시`·`암호`·`참조`. 이름이 비밀값처럼 보이는 열(`password`·`secret`·`token`·`api_key`·`private_key`·`totp`·`recovery`)은 `비밀`, 개인정보처럼 보이는 열(`email`·`phone`·`birth`·`ip`·`address_line`·`real_name`·`passport`·`card`·`bank_account`·`rrn`)은 `개인` 이상. **[검사]** `data_classes.py`
- S-SEC-3 `암호+색인` 열은 `<열>_bidx bytea`(HMAC-SHA-256 32바이트, 열마다 다른 키, 정규화 후)를 같은 테이블에 둔다. 값 종류가 적은 열에는 blind index 금지. **[검사]** `data_classes.py`(`_bidx` 열 있음) **[QA]**
- S-SEC-4 비밀번호는 Argon2id(RFC 9106 두 번째 권장: 메모리 64MiB·반복 3·병렬 1~4, 최소 OWASP 19MiB·2·1), 동시 계산 상한(세마포어). 길고 무작위인 토큰은 HMAC-SHA-256(키는 KMS)만 저장. 카드번호는 저장 금지(토큰화), CVC는 어떤 형태로도 저장 금지. **[QA]**
- S-SEC-5 `개인` 이상 값과 SQL 바인딩 값은 로그·추적·지표 라벨·오류·감사 `detail`에 넣지 않는다(서버 `log_parameter_max_length = 0`, `log_error_verbosity = terse`). **[QA]** (R-OBS-1·2)
- S-SEC-6 설계서의 테이블마다 보관 기한과 파기 방법(파티션 떼기·지우기·가명화·키 파기)을 적는다. 법정 기간은 "법무 확인" 표시. **[검사]** `data_classes.py`(테이블 절에 `보관`) **[QA]**
- S-SEC-7 DB 안에서 암호화하지 않는다(`pgcrypto`의 `pgp_sym_encrypt`·`encrypt`·`crypt` 등 금지 — 키가 SQL·로그에 실림). 필드 암호화는 엔진 `FieldCipher`. **[lint]**
- S-SEC-8 저장 장치·WAL·백업 암호화, 전송 TLS 1.3 `verifyFull`, 키 관리(KMS·HSM, 교체 주기, 사용 감사)는 database.md §9.4·§9.5. **[QA]**(운영 점검표)
- S-SEC-9 등급 `개인` 이상 열이 있는 표는 읽기 계정(`<서비스>_ro`)이 그 열을 읽지 못하게 한다: 이관기를 만드는 파일에 `const READER_HIDDEN: &[&str] = &["표", …];`(표째 감춤) 또는 `const READER_COLUMNS: &[(&str, &[&str])] = &[("표", &["열", …]), …];`(`개인` 미만 열만 엶)를 두고, 같은 파일에서 엔진 `reader_hidden`·`reader_columns`로 넘긴다(엔진 E-DB-12). 검사가 이 상수를 읽으므로 다른 모양(상수 없이 부르기, 다른 파일에서 넘기기)은 실패. 대사 계정(`_recon`)은 E-DB-15 전까지 쓰지 않는다(database.md §9.2). **[검사]** `data_classes.py`(설계서 등급 ↔ 코드 상수) `migration_apply.py`(엔진과 같은 권한 뒤 `has_column_privilege`)

## 7. 쿼리

- S-Q-1 쿼리는 매개변수 바인딩만(문자열 이어 붙이기 금지). sqlx 컴파일 시점 검사(`query!`) 사용. 식별자를 이어 붙여야 하면 엔진 `SqlName`만. **[lint]** sqlx **[QA]**
- S-Q-2 `SELECT *`(`t.*` 포함) 금지(열을 적음). 목록은 키 기반 페이지와 상한(큰 `OFFSET` 금지). **[lint]**(`.sql`과 Rust 문자열) **[QA]**(페이지)
- S-Q-3 자주 쓰는 조회는 `EXPLAIN`으로 색인을 확인하고 설계서에 적는다. N+1 금지. 외래 키 열에는 색인. **[QA]** **[벤치]**
- S-Q-4 모든 접속에 문장·잠금·유휴 트랜잭션 기한(database.md §3.3). **[검사]** 엔진 설정 검사(필수 칸) **[QA]**
- S-Q-5 트랜잭션은 짧게: 트랜잭션 안에서 다른 서비스·바깥 HTTP를 부르지 않는다. 여러 행을 잠그면 늘 같은 키 순서로(`ORDER BY 키 FOR UPDATE`, 교착 방지). **[QA]**

## 8. 접속

- S-CONN-1 서비스마다 쓰기·읽기 접속을 따로(`ServiceDatabase`). 모든 앱 서버 풀의 합 ≤ `max_connections` − 예비. 풀 대기는 짧게 기다리고 거절(503). **[QA]**
- S-CONN-2 운영 접속은 TLS `verifyFull`, 암호는 `passwordFile`(설정·저장소에 없음), 계정마다 다른 암호. **[QA]**

## 9. 이름·서식

- S-NAME-1 테이블·열은 `snake_case`, 테이블은 복수형, 외래 키는 `<대상>_id`, 시각은 `timestamptz` + `_at`, 불리언은 `is_`·`has_`, blind index는 `<열>_bidx`. **[QA]**
- S-FMT-1 키워드 대문자, 한 줄에 절 하나. **[QA]**

## 10. ClickHouse (로그·추적·지표만)

**쓰는 근거.** 로그·추적·지표 저장은 ClickHouse로 합니다(사용자 결정 2026-10-29, `docs/plan.md` 4단계 "로그 서비스(수집·처리·저장·조회, ClickHouse)", `docs/spec/observability/README.md` §3). 이 절은 규약의 일부라 관문 `waived`(예외 등록)가 아닙니다. 쓸 수 있는 곳은 다시 만들 수 없어도 되는 운영 자료(로그 줄·추적 구간·지표·그 집계)뿐입니다. 돈·권한·감사·설정처럼 지워지면 안 되는 기록은 PostgreSQL에 둡니다(로그 서비스 자신의 조회 감사도 PostgreSQL `logs` 스키마). 담당은 로그 서비스이고, 다른 서비스는 로그 서비스 API 또는 설계서 계정 표에 적힌 엔진 포트(모니터링의 `MetricStore` → `mookko_metrics`)로만 닿습니다.

이관 파일은 경로에 `clickhouse`가 든 `migrations/`(예: `crates/adapters/mookko-store-clickhouse/migrations/NNNN_이름.sql`)에 둡니다. 이 경로의 파일에는 아래 대응표의 ClickHouse 규칙이 적용됩니다.

### 10.1 PostgreSQL 규칙과의 대응

| 규칙 | ClickHouse에서 |
|---|---|
| S-BND-1 | 데이터베이스(`mookko_logs`·`mookko_traces`·`mookko_metrics`·`mookko_obs_meta`, 금융 등급 DB)의 주인은 로그 서비스 하나. 다른 서비스가 쓰거나 읽으면 설계서 계정 표에 계정·권한·이유를 적음(예: 모니터링 `mookko_metrics_rw`) **[QA]** |
| S-BND-2 | 넣기(`INSERT`만)·조회(읽기 전용)·보관(`ALTER … DROP PARTITION`·`MODIFY TTL`)·이관(DDL) 계정을 나눔 **[QA]** |
| S-BND-3·4 | 이관에 `CREATE USER`·`CREATE ROLE`·`GRANT`·서버 설정을 두지 않음(서버 준비 단계) — 단 질의 상한 프로필은 S-CH-6 **[QA]** |
| S-MIG-1 | 파일 이름 `NNNN_이름.sql`, 머리 `-- mookko:phase`, 앞으로만. 이관 기록(`mookko_obs_meta.schema_migrations`)의 키는 **(데이터베이스, 이관 ID)** **[lint]**(이름·머리) **[QA]**(기록 키) |
| S-MIG-2 | 데이터를 다시 쓰는 변경 금지: 변이·`MATERIALIZE …`·`OPTIMIZE … FINAL`(S-CH-2). 열 추가는 `ADD COLUMN … DEFAULT/MATERIALIZED`(메타데이터만) **[lint]** |
| S-MIG-3 | 기본 키 대신 `ORDER BY`(조회의 앞 조건과 같게)와 `PARTITION BY`(보관 단위, 30~60개). 원본 표에 `ORDER BY tuple()` 금지 **[lint]**(`tuple()`) **[QA]** |
| S-MIG-4 | 정렬 키·파티션 키 바꾸기는 세 배포: 넓히기(새 표 + 새 MV, 두 표에 함께 넣음) → 옮기기(기간별 `INSERT … SELECT`, 읽기를 새 표로) → 좁히기(옛 MV·표 지우기·`RENAME`/`EXCHANGE`). 지우기·이름 바꾸기는 `contract` 파일에서만 **[lint]**(지우기·이름 바꾸기) **[QA]**(배포 나누기) |
| S-MIG-5·6 | 해당 없음(ClickHouse `ALTER`는 넣기를 막지 않음, 트랜잭션 DDL 없음 → S-CH-7) |
| S-TYPE-* | 시각은 `DateTime64(9)`·`DateTime`(UTC), 낮은 종류 글자는 `LowCardinality(String)`, 돈 열 없음(지표 값 `Float64`만 허용 — 돈 아님, 계산은 정수로 R-SAFE-4) **[QA]** |
| S-SEC-* | 그대로(열마다 등급·보호, 가림 규칙). 개인 이상 값은 넣기 전에 가림. 지울 일이 생기면 HMAC 키 파기 또는 파티션 떼기 **[검사]** `data_classes.py` |
| S-Q-1·2·4 | 매개변수 `{name:Type}`만, `SELECT *` 금지, 모든 조회에 상한(S-CH-6) **[lint]**(`SELECT *`) **[QA]** |
| S-Q-3 | 자주 쓰는 조회마다 `EXPLAIN indexes = 1`(읽은 덩어리 수)을 설계서에 **[QA]** |
| S-NAME-1 | 수집기 내보내기가 넣는 표와 그 표를 그대로 묶는 MV 대상 표는 수집기 열 이름(`PascalCase`)을 씀(MV 열 이름이 원본과 같아야 함). 그 밖의 표(`mookko_obs_meta` 등)는 `snake_case` **[QA]** (S-CH-3) |

### 10.2 ClickHouse 규칙

- S-CH-1 `MergeTree` 계열 표는 모두 `TTL`(보관 기한)을 두고, `SETTINGS materialize_ttl_after_modify = 0`(보관 기한을 바꿀 때 전체 조각을 다시 쓰지 않게). 한 표에 보관 기한이 다른 등급(일반·보안·금융)의 행이 섞이면 등급 열 + `TTL … DELETE WHERE <등급 열> = …`로 나누거나 데이터베이스를 나눔(정하지 않으면 가장 긴 기한이 짧은 등급까지 남기는 셈) **[lint]**(TTL·설정) **[QA]**(등급별 기한)
- S-CH-2 데이터를 고치는 변이(`ALTER TABLE … UPDATE`·`… DELETE WHERE`, 가벼운 `DELETE FROM`·`UPDATE`)와 `MATERIALIZE COLUMN|INDEX|TTL|PROJECTION`, `OPTIMIZE … FINAL` 금지(전체 조각을 다시 씀). 지우기는 TTL·`DROP PARTITION`으로 **[lint]**
- S-CH-3 이름 규칙은 10.1 S-NAME-1 줄 **[QA]**
- S-CH-4 이관 SQL의 표·MV 이름은 모두 데이터베이스를 붙여 씀(`mookko_logs.otel_logs`). 같은 이관을 여러 데이터베이스(예: 금융 등급 DB)에 쓰면 `__DB__.표` 자리 표시를 쓰고 어댑터 이관기가 바꿈(MV 본문의 `FROM`·`TO`도) **[lint]**
- S-CH-5 **중복 막기.** 일반(복제 아닌) `MergeTree`는 기본으로 중복 블록을 거르지 않으므로(`non_replicated_deduplication_window = 0`), 넣는 쪽이 다시 보낼 수 있는 표는 `SETTINGS non_replicated_deduplication_window = <N>`(예: 1000)을 두고, 넣는 계정 프로필에 `insert_deduplicate = 1`, `deduplicate_blocks_in_dependent_materialized_views = 1`을 둠(MV 집계가 두 번 더해지지 않게). 넣는 쪽은 묶음마다 `insert_deduplication_token`을 붙임. `Replicated*MergeTree`는 기본으로 거름 **[lint]**(표 설정) **[QA]**(프로필·토큰). 그래도 남는 오차(창 밖 재전송)는 설계서에 허용 범위로 적음
- S-CH-6 **질의 상한.** 조회 계정 프로필은 `readonly = 1`(설정 바꾸기 금지)이 기본이고, `readonly = 2`(질의마다 설정)를 쓰면 `max_execution_time`·`max_memory_usage`·`max_rows_to_read`·`max_result_rows`를 `MAX …` 또는 `CONST`(`READONLY`)로 묶음. 이관에서 `CREATE|ALTER SETTINGS PROFILE`을 쓰면 검사가 이것을 봄 **[lint]** **[QA]**(서버 설정 파일의 프로필)
- S-CH-7 **이관 실패 복구.** ClickHouse에는 트랜잭션 DDL이 없어 파일 중간에서 멈출 수 있으므로, 모든 문장은 다시 해도 안전하게 씀: `CREATE … IF NOT EXISTS`, `ADD COLUMN|INDEX|PROJECTION IF NOT EXISTS`, `DROP … IF EXISTS`. 이관기는 문장마다 기록하거나 실패한 파일을 처음부터 다시 돌리고, 한 번에 하나만 돎(이관 단계 잠금, 엔진 순서표의 이관 동시 실행 안전) **[lint]**(IF [NOT] EXISTS) **[QA]**(이관기)

## 11. 설계서(`data-model.md`) 형식 — 검사가 읽음

테이블마다 제목에 테이블 이름을 백틱으로 적고(`### \`audit_events\``), 그 아래 열 표에 `열`·`형식`·`등급`·`보호` 칸을 둔다. 테이블 절 안에 `보관`(기한·파기 방법) 문장이 있어야 한다.

```markdown
### `accounts`

| 열 | 형식 | 제약 | 등급 | 보호 | 뜻 |
|---|---|---|---|---|---|
| `account_id` | `uuid` | PK | 내부 | 평문 | UUIDv7 |
| `email` | `text` | NOT NULL | 개인 | 암호+색인 | 로그인 이메일 |
| `email_bidx` | `bytea` | UNIQUE, 32바이트 | 내부 | 평문 | `email`의 blind index |

보관: 탈퇴 즉시 `email`을 지우고 행은 가명으로 남김.
```

- SQL 코드 블록(`CREATE TABLE`)으로 적은 테이블(ClickHouse 등)은 따로 `| 테이블 | 열 | 등급 | 보호 |` 표에 열마다 적는다. 같은 등급인 나머지 열은 `열` 칸에 `(나머지)` 한 줄로 묶을 수 있다.
- 엔진 테이블처럼 서비스가 이름을 정하는 테이블은 제목에 꺾쇠 자리 표시로 적는다(`### \`<원장>_heads\``).
- 이름이 비밀값·개인정보처럼 보이지만 아닌 열(예: 개수 `token_count`)은 그 줄에 `이름 예외: <이유>`를 적는다.
- 이 규약 전에 들어온 이관·설계서는 `scripts/ci/db/pending.json`에 담당·기한과 함께 올라 있고, 기한까지는 경고만, 지나면 검사가 실패한다. 새 파일은 처음부터 실패. 목록은 DB 담당만 고친다.

//! 표본(통과해야 함): 이관 폴더를 엔진 `add_dir`로 읽고, 덧붙이기만 하는 원장을 `append_only`로 지정하는 서비스.
//! 검사(migration_lint.py `lint_embedded`)만 읽는 글이고 빌드하지 않는다.

/// 원장 테이블(앱 계정은 SELECT·INSERT만).
const LEDGER_TABLE: &str = "ledger_entries";

/// 읽기 계정(`svc_ro`)이 이 열만 읽는 표(개인 등급 `email`을 감춤, S-SEC-9).
const READER_COLUMNS: &[(&str, &[&str])] = &[("accounts", &["account_id", "state", "created_at", "closed_at", "region"])];

// migrator: SchemaMigrator::new(schema).add_dir(dir).await?.append_only(&SqlName::parse(LEDGER_TABLE)?)
fn reader(mut migrator: SchemaMigrator) -> Result<SchemaMigrator, DataError> {
    for (table, columns) in READER_COLUMNS {
        migrator = migrator.reader_columns(&SqlName::parse(table)?, &names(columns)?);
    }
    Ok(migrator)
}

// 통과해야 할 글(SQL 문장이 아님): 감사 동작 이름·식별자·낱말 하나·설명 글.
const ACTIONS: &[&str] = &["handle.revoke", "revoke_handle", "grant", "truncate", "drop", "staff.grant_role"];
const MESSAGE: &str = "cannot revoke the last admin; ask another admin to grant access";

// 고정 파일을 엔진 도우미로 넣는 모양(시험용 글): migrator.add_generated("0001_accounts_and_ledger", &engine_sql, include_str!("../migrations/0001_accounts_and_ledger.sql"))

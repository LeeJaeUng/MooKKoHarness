//! 표본(통과해야 함): 이관 폴더를 엔진 `add_dir`로 읽고, 덧붙이기만 하는 원장을 `append_only`로 지정하는 서비스.
//! 검사(migration_lint.py `lint_embedded`)만 읽는 글이고 빌드하지 않는다.

/// 원장 테이블(앱 계정은 SELECT·INSERT만).
const LEDGER_TABLE: &str = "ledger_entries";

// migrator: SchemaMigrator::new(schema).add_dir(dir).await?.append_only(&SqlName::parse(LEDGER_TABLE)?)

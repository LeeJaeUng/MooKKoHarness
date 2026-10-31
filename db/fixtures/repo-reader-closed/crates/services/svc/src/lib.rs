//! 표본(S-SEC-9 닫힌 기본): 읽기 계정은 정한 표만 봄. `notes`(민감 `body`)를 표째 연 것만 잡아야 함.
//! 검사(data_classes.py `reader_coverage`)만 읽고 빌드하지 않는다.

const READER_TABLES: &[&str] = &["notes"];

fn reader(mut migrator: SchemaMigrator) -> Result<SchemaMigrator, DataError> {
    for table in READER_TABLES {
        migrator = migrator.reader_table(&SqlName::parse(table)?);
    }
    Ok(migrator)
}

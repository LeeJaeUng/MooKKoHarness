//! 표본: 엔진 공유 이관기가 감출 표를 상수로 두고 넘김.

const READER_HIDDEN: &[&str] = &["staff_sessions"];

fn shared(mut migrator: SchemaMigrator) -> Result<SchemaMigrator, DataError> {
    for table in READER_HIDDEN {
        migrator = migrator.reader_hidden(&SqlName::parse(table)?);
    }
    Ok(migrator)
}

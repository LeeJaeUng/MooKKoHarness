//! 표본: 상수는 있지만 엔진에 넘기지 않음. `reader_hidden` 호출은 있지만 다른 표를 글자로 넘김(QA 795bf8c: 호출 글자만 보면 통과하던 것).

const READER_HIDDEN: &[&str] = &["visits"];

fn other(migrator: SchemaMigrator) -> Result<SchemaMigrator, DataError> {
    let table = SqlName::parse("people")?;
    Ok(migrator.reader_hidden(&table))
}

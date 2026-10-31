//! 표본(S-SEC-9가 잡아야 함): 읽기 계정 설정이 틀린 서비스. 검사(data_classes.py `reader_coverage`)만 읽고 빌드하지 않는다.
//! - `people`: 열만 연다면서 개인 등급 `email`을 엶.
//! - `notes`: 설정이 아예 없음.
//! - `missing_table`: 이관이 만들지 않는 표의 열을 엶.
//! - `visits`: 감춘다고 적었지만 `READER_HIDDEN`을 `reader_hidden`으로 넘기지 않음(아래 파일 hidden.rs).

const READER_COLUMNS: &[(&str, &[&str])] = &[("people", &["person_id", "email"]), ("missing_table", &["id"])];

fn reader(mut migrator: SchemaMigrator) -> Result<SchemaMigrator, DataError> {
    for (table, columns) in READER_COLUMNS {
        migrator = migrator.reader_columns(&SqlName::parse(table)?, &names(columns)?);
    }
    Ok(migrator)
}

//! 표본(S-PART-3): `visits`만 엔진 `partitioned`로 적음. `events`는 이름만 있고(쿼리 글) 적지 않음.
//! 검사(migration_lint.py `lint_partitioned`)만 읽고 빌드하지 않는다.

const EVENTS: &str = "events";

fn partitions(migrator: SchemaMigrator) -> Result<SchemaMigrator, DataError> {
    let visits = PartitionedTable::monthly(SqlName::parse("visits")?, PartitionKey::Date).keep_days(90);
    Ok(migrator.partitioned(visits))
}

// migrator.partitioned(PartitionedTable::monthly(SqlName::parse("events")?, PartitionKey::TimestampUtc)) — 주석은 세지 않음

/* 블록 주석 안의 등록도 세지 않음(QA f4753d1):
   migrator.partitioned(PartitionedTable::monthly(SqlName::parse("events")?, PartitionKey::TimestampUtc)) */
const QUOTE: char = '"';

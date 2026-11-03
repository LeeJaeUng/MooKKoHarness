//! 표본(S-TIME-1): 서비스 SQL의 DB 시계·ID 함수. 빌드하지 않는다. 주석 안 now()는 세지 않음.

const CLAIM: &str = "UPDATE svc.jobs SET claimed_at = now() WHERE job_id = $1";
const INSERT_EVENT: &str = "INSERT INTO svc.audit_events (event_id, at) VALUES (uuidv7(), $1)";
const OK_BOUND: &str = "UPDATE svc.jobs SET claimed_at = $2 WHERE job_id = $1 -- now() 대신 $now";
const DAY: &str = "SELECT date_trunc('day', at) FROM svc.audit_events WHERE at >= $1";
const DAY_UTC: &str = "SELECT date_trunc('day', at AT TIME ZONE 'UTC') FROM svc.audit_events WHERE at >= $1";

fn register(migrator: SchemaMigrator) -> Result<SchemaMigrator, DataError> {
    // 감사 파티션인데 keep_days·archive_before_drop 없음(잡아야 함)
    Ok(migrator.partitioned(PartitionedTable::monthly(SqlName::parse("audit_events")?, PartitionKey::TimestampUtc)))
}

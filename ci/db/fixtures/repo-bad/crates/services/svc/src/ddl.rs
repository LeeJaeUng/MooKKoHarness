// 표본: 서비스 코드가 이관 밖에서 구조를 바꿈(잡아야 함). 주석의 ALTER TABLE은 보지 않음.
const WIDEN: &str = "ALTER TABLE svc.items ADD COLUMN note text";
const OK: &str = "SELECT item_id FROM svc.items WHERE item_id = $1";
const DROP_AFTER_SET: &str = "SET LOCAL lock_timeout = '3s'; DROP TABLE IF EXISTS svc.old_items";
const GRANT_SQL: &str = "GRANT SELECT ON svc.items TO svc_ro";
const COMMENT_FIRST: &str = "-- 달 파티션을 미리 만듦\nCREATE TABLE IF NOT EXISTS svc.events_202612 PARTITION OF svc.events FOR VALUES FROM (2) TO (3)";
const BLOCK_COMMENT_FIRST: &str = r#"/* 보관 기한 지난 달 */
ALTER TABLE svc.events DETACH PARTITION svc.events_202601 CONCURRENTLY"#;

pub const SQLS: [&str; 5] = [
    "OPTIMIZE TABLE mookko_logs_sec.sec_events PARTITION 202611 FINAL",
    "ALTER TABLE mookko_logs.events UPDATE body = '' WHERE id = {id:UInt64}",
    "ALTER TABLE mookko_logs.events MATERIALIZE INDEX idx_body",
    "DELETE FROM links.handles WHERE id = $1",
    "SELECT count() FROM mookko_logs.events FINAL",
];

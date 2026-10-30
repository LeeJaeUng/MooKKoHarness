-- expect: (없음)
-- mookko:phase expand
CREATE TABLE IF NOT EXISTS __DB__.raw_counts
(
    Minute DateTime,
    Records UInt64
)
ENGINE = ReplicatedSummingMergeTree(Records)
PARTITION BY toYYYYMM(Minute)
ORDER BY Minute
TTL Minute + INTERVAL 400 DAY DELETE
SETTINGS materialize_ttl_after_modify = 0;
CREATE MATERIALIZED VIEW IF NOT EXISTS __DB__.raw_counts_mv TO __DB__.raw_counts AS
SELECT toStartOfMinute(Ts) AS Minute, count() AS Records
FROM __DB__.raw
GROUP BY Minute;
CREATE SETTINGS PROFILE IF NOT EXISTS mookko_logs_query SETTINGS readonly = 2, max_execution_time = 10 MAX 10, max_memory_usage = 1073741824 MAX 1073741824, max_rows_to_read = 100000000 MAX 100000000, max_result_rows = 10000 CONST;

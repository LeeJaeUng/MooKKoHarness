-- expect: S-CH-4
-- mookko:phase expand
CREATE MATERIALIZED VIEW IF NOT EXISTS mookko_logs.raw_counts_mv TO raw_counts AS
SELECT toStartOfMinute(Ts) AS Minute, count() AS Records
FROM raw
GROUP BY Minute;

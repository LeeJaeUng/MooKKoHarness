-- expect: (없음)
-- mookko:phase expand
CREATE TABLE IF NOT EXISTS mookko_logs.raw
(
    Ts DateTime CODEC(Delta(4), ZSTD(1)),
    Body String,
    INDEX idx_body lower(Body) TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 1
)
ENGINE = MergeTree
PARTITION BY toDate(Ts)
ORDER BY Ts
TTL Ts + INTERVAL 1 DAY DELETE WHERE length(Body) > 0, Ts + INTERVAL 45 DAY DELETE
SETTINGS materialize_ttl_after_modify = 0, non_replicated_deduplication_window = 1000;
ALTER TABLE mookko_logs.raw MODIFY TTL Ts + INTERVAL 30 DAY DELETE;
ALTER TABLE mookko_logs.raw ADD COLUMN IF NOT EXISTS HostId String MATERIALIZED Body;

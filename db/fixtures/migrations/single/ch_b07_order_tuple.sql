-- expect: S-MIG-3
-- mookko:phase expand
CREATE TABLE IF NOT EXISTS mookko_logs.raw (Ts DateTime, Body String)
ENGINE = MergeTree ORDER BY tuple()
TTL Ts + INTERVAL 1 DAY DELETE
SETTINGS materialize_ttl_after_modify = 0, non_replicated_deduplication_window = 1000;

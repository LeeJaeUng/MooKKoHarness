-- expect: (없음)
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';
CREATE INDEX IF NOT EXISTS events_kind ON ONLY __SCHEMA__.old_events (kind);
ALTER INDEX __SCHEMA__.events_kind ATTACH PARTITION __SCHEMA__.events_2026_10_kind;

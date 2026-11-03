-- mookko:transaction off
-- expect: (없음)
-- mookko:phase expand
-- mookko:expected 30
CREATE INDEX CONCURRENTLY IF NOT EXISTS events_2026_10_kind ON __SCHEMA__.events_2026_10 (kind);

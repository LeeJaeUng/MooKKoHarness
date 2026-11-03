-- expect: (없음)
-- mookko:phase expand
-- mookko:expected 30
-- mookko:transaction off
CREATE INDEX CONCURRENTLY IF NOT EXISTS old_items_a ON __SCHEMA__.old_items (a);

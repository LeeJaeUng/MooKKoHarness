-- mookko:transaction off
-- expect: S-MIG-12
-- mookko:phase expand
-- mookko:expected 301
CREATE INDEX CONCURRENTLY IF NOT EXISTS old_items_a ON __SCHEMA__.old_items (a);

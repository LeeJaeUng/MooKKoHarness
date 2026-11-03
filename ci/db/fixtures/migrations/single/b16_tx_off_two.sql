-- mookko:transaction off
-- expect: S-MIG-6
-- mookko:phase expand
CREATE INDEX CONCURRENTLY IF NOT EXISTS i1 ON __SCHEMA__.old_items (a);
CREATE INDEX CONCURRENTLY IF NOT EXISTS i2 ON __SCHEMA__.old_items (b);

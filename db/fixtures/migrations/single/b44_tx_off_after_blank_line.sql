-- expect: S-MIG-6
-- mookko:phase expand

-- mookko:transaction off
CREATE INDEX CONCURRENTLY IF NOT EXISTS old_items_a ON __SCHEMA__.old_items (a);

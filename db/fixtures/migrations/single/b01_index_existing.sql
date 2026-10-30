-- expect: S-MIG-2a
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';
CREATE INDEX old_items_a ON __SCHEMA__.old_items (a);

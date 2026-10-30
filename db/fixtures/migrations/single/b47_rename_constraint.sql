-- expect: S-MIG-4
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_items RENAME CONSTRAINT old_items_a_key TO old_items_a_unique;

-- expect: S-MIG-2g
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_items ADD CONSTRAINT old_items_a_key UNIQUE (a);

-- expect: S-MIG-5
-- mookko:phase expand
SET LOCAL lock_timeout = '30s';
ALTER TABLE __SCHEMA__.old_items ADD COLUMN note text;

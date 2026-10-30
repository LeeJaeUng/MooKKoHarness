-- expect: S-MIG-2g
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_items ADD COLUMN code text UNIQUE;

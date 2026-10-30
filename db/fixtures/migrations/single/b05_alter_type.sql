-- expect: S-MIG-2d
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_items ALTER COLUMN a TYPE bigint;

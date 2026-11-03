-- expect: S-MIG-2e
-- mookko:phase migrate
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_items ALTER COLUMN a SET NOT NULL;

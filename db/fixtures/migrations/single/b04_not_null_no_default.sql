-- expect: S-MIG-2c
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_items ADD COLUMN note text NOT NULL;

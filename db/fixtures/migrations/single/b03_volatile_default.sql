-- expect: S-MIG-2b
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_items ADD COLUMN token_id uuid DEFAULT gen_random_uuid();

-- expect: S-MIG-2f
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_items ADD COLUMN owner2_id uuid REFERENCES __SCHEMA__.owners (owner_id);

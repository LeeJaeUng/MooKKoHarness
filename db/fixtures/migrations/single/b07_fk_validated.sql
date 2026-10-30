-- expect: S-MIG-2f
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_items ADD CONSTRAINT old_items_owner_fkey FOREIGN KEY (owner_id) REFERENCES __SCHEMA__.owners (owner_id);

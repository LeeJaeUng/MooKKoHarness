-- expect: S-MIG-7
-- mookko:phase migrate
SET LOCAL lock_timeout = '3s';
UPDATE __SCHEMA__.old_items SET a = 1 WHERE a IS NULL;

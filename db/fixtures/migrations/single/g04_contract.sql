-- expect: (없음)
-- mookko:phase contract
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_items DROP COLUMN legacy_note;
DROP TABLE __SCHEMA__.old_unused;

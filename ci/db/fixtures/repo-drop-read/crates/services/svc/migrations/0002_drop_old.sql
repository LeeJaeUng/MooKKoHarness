-- mookko:phase contract
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.items DROP COLUMN old_note;
DROP TABLE __SCHEMA__.olds;

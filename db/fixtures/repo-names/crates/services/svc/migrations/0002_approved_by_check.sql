-- mookko:phase expand
SET LOCAL lock_timeout = '3s';

ALTER TABLE __SCHEMA__.actions ADD CONSTRAINT actions_approved_by CHECK (approved_by IS NULL OR (char_length(approved_by) BETWEEN 1 AND 200 AND approved_by ~ '^[!-~]([ -~]*[!-~])?$')) NOT VALID;

-- mookko:phase expand
SET LOCAL lock_timeout = '3s';

ALTER TABLE __SCHEMA__.items ADD CONSTRAINT items_kind_lower CHECK (kind = lower(kind)) NOT VALID;

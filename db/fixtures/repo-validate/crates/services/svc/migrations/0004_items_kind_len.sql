-- mookko:phase expand
SET LOCAL lock_timeout = '3s';

ALTER TABLE __SCHEMA__.items ADD CONSTRAINT items_kind_len CHECK (char_length(kind) <= 8) NOT VALID;

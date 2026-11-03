-- mookko:phase migrate
SET LOCAL lock_timeout = '3s';

ALTER TABLE __SCHEMA__.items VALIDATE CONSTRAINT items_kind_lower;

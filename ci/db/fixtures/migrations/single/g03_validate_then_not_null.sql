-- expect: (없음)
-- mookko:phase migrate
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_items VALIDATE CONSTRAINT old_items_a_nn;
ALTER TABLE __SCHEMA__.old_items ALTER COLUMN a SET NOT NULL;
ALTER TABLE __SCHEMA__.old_items DROP CONSTRAINT old_items_a_nn;

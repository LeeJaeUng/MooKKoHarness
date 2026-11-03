-- expect: S-MIG-12
-- mookko:phase migrate
-- mookko:expected 5m
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_items VALIDATE CONSTRAINT old_items_a_nn;

-- mookko:phase migrate
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.accounts VALIDATE CONSTRAINT accounts_region_nn;
ALTER TABLE __SCHEMA__.accounts ALTER COLUMN region SET NOT NULL;
ALTER TABLE __SCHEMA__.accounts DROP CONSTRAINT accounts_region_nn;

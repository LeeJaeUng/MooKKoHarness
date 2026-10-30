-- mookko:phase contract
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.accounts DROP COLUMN tier;

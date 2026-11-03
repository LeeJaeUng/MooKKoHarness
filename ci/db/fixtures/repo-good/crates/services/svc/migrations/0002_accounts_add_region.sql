-- mookko:phase expand
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.accounts ADD COLUMN closed_at timestamptz;
ALTER TABLE __SCHEMA__.accounts ADD COLUMN region text;
ALTER TABLE __SCHEMA__.accounts ADD COLUMN tier text NOT NULL DEFAULT 'basic';
ALTER TABLE __SCHEMA__.accounts ADD CONSTRAINT accounts_region_nn CHECK (region IS NOT NULL) NOT VALID;

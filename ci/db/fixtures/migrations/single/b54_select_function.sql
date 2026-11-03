-- expect: S-MIG-9
-- mookko:phase migrate
CREATE FUNCTION __SCHEMA__.backfill() RETURNS void LANGUAGE sql AS $$ UPDATE __SCHEMA__.old_items SET a = 1 $$;
SELECT __SCHEMA__.backfill();

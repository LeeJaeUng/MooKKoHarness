-- expect: S-MIG-9
-- mookko:phase migrate
CREATE PROCEDURE __SCHEMA__.wipe() LANGUAGE sql AS $$ DELETE FROM __SCHEMA__.audit_events $$;
CALL __SCHEMA__.wipe();

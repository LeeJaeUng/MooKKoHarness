-- expect: S-MIG-9
-- mookko:phase migrate
DO $$
BEGIN
    UPDATE __SCHEMA__.old_items SET a = 1;
    ALTER TABLE __SCHEMA__.audit_events DISABLE TRIGGER ALL;
END
$$;

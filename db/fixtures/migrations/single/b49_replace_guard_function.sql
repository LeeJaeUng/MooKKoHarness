-- expect: S-MIG-9
-- mookko:phase migrate
CREATE OR REPLACE FUNCTION __SCHEMA__.reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RETURN NEW;
END
$$;

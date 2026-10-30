-- expect: S-BND-6
-- mookko:phase expand
CREATE FUNCTION __SCHEMA__.f() RETURNS integer LANGUAGE sql SECURITY DEFINER AS $$ SELECT 1 $$;

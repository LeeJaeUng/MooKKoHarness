-- 잡아야 함(S-BND-6): search_path 값이 public, 스키마 없이 부르는 자기 함수
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';

CREATE FUNCTION __SCHEMA__.tags_public_path(items text[]) RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = public, pg_catalog AS $$
    SELECT true
$$;

ALTER TABLE __SCHEMA__.events ADD CONSTRAINT events_tags_public CHECK (__SCHEMA__.tags_public_path(tags)) NOT VALID;
ALTER TABLE __SCHEMA__.events ADD CONSTRAINT events_tags_bare CHECK (tags_ok(tags) AND cardinality(tags) < 9) NOT VALID;

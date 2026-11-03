-- 표본(S-MIG-2·S-BND-6): 파티션 부모와 CHECK가 부를 함수들
-- mookko:phase expand

CREATE TABLE __SCHEMA__.events (
    event_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL,
    tags text[],
    CONSTRAINT events_pkey PRIMARY KEY (event_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE FUNCTION __SCHEMA__.tags_ok(items text[]) RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog AS $$
    SELECT count(*) = count(DISTINCT item) FROM unnest(items) AS item
$$;

CREATE FUNCTION __SCHEMA__.tags_volatile(items text[]) RETURNS boolean LANGUAGE sql SET search_path = pg_catalog AS $$
    SELECT true
$$;

CREATE FUNCTION __SCHEMA__.tags_fixed_later(items text[]) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
    SELECT true
$$;

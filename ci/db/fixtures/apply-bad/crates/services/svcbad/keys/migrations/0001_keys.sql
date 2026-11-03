-- 적용 시험이 잡아야 할 것(키 DB, S-SEC-10): 기본 키가 subject_id만, 보기·함수, 읽기 계정 스키마 USAGE
-- mookko:phase expand

CREATE TABLE __SCHEMA__.row_keys (
    subject_id uuid NOT NULL,
    purpose text NOT NULL,
    wrapped_key bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT row_keys_pkey PRIMARY KEY (subject_id)
);
CREATE VIEW __SCHEMA__.row_key_counts AS SELECT purpose, count(*) AS n FROM __SCHEMA__.row_keys GROUP BY purpose;
CREATE FUNCTION __SCHEMA__.noop() RETURNS integer LANGUAGE sql AS $$ SELECT 1 $$;
GRANT USAGE ON SCHEMA __SCHEMA__ TO svcbad_keys_ro;

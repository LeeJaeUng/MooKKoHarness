-- 표본(S-TIME-1): 함수 밖 DEFAULT now()는 잡고, 트리거 함수 안의 하한은 둠
-- mookko:phase expand

CREATE TABLE __SCHEMA__.jobs (
    job_id uuid NOT NULL,
    claimed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT jobs_pkey PRIMARY KEY (job_id)
);

CREATE FUNCTION __SCHEMA__.jobs_not_late() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    IF NEW.claimed_at < now() - interval '1 hour' THEN
        RAISE EXCEPTION 'late' USING ERRCODE = '22007';
    END IF;
    RETURN NEW;
END
$$;

CREATE TABLE __SCHEMA__.audit_events (
    event_id uuid NOT NULL,
    at timestamptz NOT NULL,
    CONSTRAINT audit_events_pkey PRIMARY KEY (event_id, at)
) PARTITION BY RANGE (at);

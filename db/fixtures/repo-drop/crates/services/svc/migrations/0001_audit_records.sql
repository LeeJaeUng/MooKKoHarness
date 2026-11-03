-- 표본(통과해야 함): 옛 덧붙이기만 표. 0002 contract가 지우므로 서비스 이관기 append_only 목록에 없어도 됨(links 0024).
-- mookko:phase expand

CREATE FUNCTION __SCHEMA__.reject_change() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    RAISE EXCEPTION 'append-only table %', TG_TABLE_NAME USING ERRCODE = '42501';
END
$$;

CREATE TABLE __SCHEMA__.audit_records (
    record_id uuid NOT NULL,
    at timestamptz NOT NULL,
    CONSTRAINT audit_records_pkey PRIMARY KEY (record_id)
);

CREATE TRIGGER audit_records_append_only BEFORE UPDATE OR DELETE ON __SCHEMA__.audit_records FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.reject_change();
CREATE TRIGGER audit_records_no_truncate BEFORE TRUNCATE ON __SCHEMA__.audit_records FOR EACH STATEMENT EXECUTE FUNCTION __SCHEMA__.reject_change();

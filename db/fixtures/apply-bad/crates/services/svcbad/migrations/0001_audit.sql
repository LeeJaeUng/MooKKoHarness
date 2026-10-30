-- 적용 시험이 잡아야 할 것: 앱 계정 UPDATE 권한, TRUNCATE 막기 없음, numeric, 기본 키 없음(글 검사를 우회한 모양)
-- mookko:phase expand
CREATE FUNCTION __SCHEMA__.reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'append-only table %', TG_TABLE_NAME USING ERRCODE = '42501';
END
$$;
CREATE TABLE __SCHEMA__.audit_events (event_id uuid PRIMARY KEY, amount numeric(10, 2));
CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON __SCHEMA__.audit_events FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.reject_change();
CREATE TABLE __SCHEMA__.loose_rows AS SELECT 1 AS n;
GRANT USAGE ON SCHEMA __SCHEMA__ TO svcbad_app;
GRANT SELECT, INSERT, UPDATE ON __SCHEMA__.audit_events TO svcbad_app;
GRANT TRUNCATE ON __SCHEMA__.loose_rows TO svcbad_app;

-- 적용 시험이 잡아야 할 것(글 검사를 우회한 모양): TRUNCATE 막기 없음, 거부하지 않는 막기 함수, numeric, 기본 키 없음, 앱 계정 스키마 CREATE
-- mookko:phase expand
CREATE FUNCTION __SCHEMA__.reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'append-only table %', TG_TABLE_NAME USING ERRCODE = '42501';
END
$$;
CREATE FUNCTION __SCHEMA__.allow_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RETURN NEW;
END
$$;
CREATE TABLE __SCHEMA__.audit_events (event_id uuid PRIMARY KEY, amount numeric(10, 2));
CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON __SCHEMA__.audit_events FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.reject_change();
CREATE TABLE __SCHEMA__.audit_log (log_id uuid PRIMARY KEY);
CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON __SCHEMA__.audit_log FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.allow_change();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON __SCHEMA__.audit_log FOR EACH STATEMENT EXECUTE FUNCTION __SCHEMA__.reject_change();
CREATE TABLE __SCHEMA__.loose_rows AS SELECT 1 AS n;
GRANT CREATE ON SCHEMA __SCHEMA__ TO svcbad_app;

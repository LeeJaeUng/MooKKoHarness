-- 적용 시험이 잡아야 할 것(글 검사를 우회한 모양): TRUNCATE 막기 없음, 거부하지 않는 막기 함수, numeric, 기본 키 없음, 앱 계정 스키마 CREATE,
-- blind index 모양(E-DB-7): 형식·32바이트·색인·키 ID 열 없음, NOT NULL 다름, 같이 비게 하는 CHECK 없음, 키 ID 모양 CHECK가 다름,
-- CHECK 정의 전체 맞춤(`= 320`·`OR true`는 잡고, 맞는 NULL 짝 CHECK는 통과)
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
CREATE TABLE __SCHEMA__.members (
    member_id uuid PRIMARY KEY,
    email_bidx text NOT NULL,
    phone_bidx bytea CHECK (octet_length(phone_bidx) = 32),
    phone_bidx_kid text NOT NULL CHECK (phone_bidx_kid ~ '^[A-Za-z0-9_-]{1,32}$'),
    alias_bidx bytea CHECK (octet_length(alias_bidx) = 32),
    alias_bidx_kid text CHECK (alias_bidx_kid ~ '^[a-z]+$')
);
CREATE INDEX members_phone_bidx ON __SCHEMA__.members (phone_bidx);
CREATE INDEX members_alias_bidx ON __SCHEMA__.members (alias_bidx);
CREATE TABLE __SCHEMA__.contacts (
    contact_id uuid PRIMARY KEY,
    note_bidx bytea CHECK (octet_length(note_bidx) = 32),
    note_bidx_kid text CHECK (note_bidx_kid ~ '^[A-Za-z0-9_-]{1,32}$'),
    wide_bidx bytea NOT NULL CHECK (octet_length(wide_bidx) = 320),
    wide_bidx_kid text NOT NULL CHECK (wide_bidx_kid ~ '^[A-Za-z0-9_-]{1,32}$' OR true),
    CONSTRAINT contacts_note_pair CHECK ((note_bidx IS NULL) = (note_bidx_kid IS NULL))
);
CREATE INDEX contacts_note_bidx ON __SCHEMA__.contacts (note_bidx);
CREATE INDEX contacts_wide_bidx ON __SCHEMA__.contacts (wide_bidx);
GRANT CREATE ON SCHEMA __SCHEMA__ TO svcbad_app;

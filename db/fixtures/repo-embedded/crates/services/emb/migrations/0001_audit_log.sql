-- mookko:phase expand
CREATE FUNCTION __SCHEMA__.reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'no';
END
$$;
CREATE TABLE __SCHEMA__.audit_log (log_id uuid PRIMARY KEY);
CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON __SCHEMA__.audit_log FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.reject_change();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON __SCHEMA__.audit_log FOR EACH STATEMENT EXECUTE FUNCTION __SCHEMA__.reject_change();

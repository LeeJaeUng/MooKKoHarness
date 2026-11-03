-- expect: S-MONEY-2
-- mookko:phase migrate
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.audit_events ENABLE REPLICA TRIGGER audit_events_append_only;

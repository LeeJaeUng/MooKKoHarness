-- expect: S-MONEY-2
-- mookko:phase migrate
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.audit_events DISABLE TRIGGER ALL;

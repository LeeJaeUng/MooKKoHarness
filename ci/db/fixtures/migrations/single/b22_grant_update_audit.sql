-- expect: S-MONEY-2
-- mookko:phase expand
GRANT SELECT, INSERT, UPDATE, DELETE ON __SCHEMA__.audit_events TO svc_app;

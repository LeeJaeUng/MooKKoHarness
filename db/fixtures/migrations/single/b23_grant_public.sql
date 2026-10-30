-- expect: S-BND-5
-- mookko:phase expand
GRANT SELECT ON __SCHEMA__.items TO PUBLIC;
GRANT SELECT ON __SCHEMA__.items TO billing_app;
GRANT ALL ON __SCHEMA__.items TO svc_app;

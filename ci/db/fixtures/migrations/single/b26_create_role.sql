-- expect: S-BND-4
-- mookko:phase expand
CREATE ROLE svc_extra LOGIN;
ALTER SYSTEM SET work_mem = '1GB';

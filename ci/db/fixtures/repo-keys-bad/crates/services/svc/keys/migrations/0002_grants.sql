-- 잡아야 함(S-SEC-10): 키 DB 읽기·대사 계정, 앱 UPDATE·TRUNCATE, 키 표 열 더하기
-- mookko:phase expand

GRANT SELECT ON __SCHEMA__.row_keys TO svc_keys_ro;
GRANT SELECT ON __SCHEMA__.row_keys TO svc_keys_recon;
GRANT UPDATE, TRUNCATE ON __SCHEMA__.row_keys TO svc_keys_app;
ALTER TABLE __SCHEMA__.row_keys ADD COLUMN note text;

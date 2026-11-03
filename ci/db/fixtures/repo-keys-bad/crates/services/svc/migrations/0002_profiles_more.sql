-- 잡아야 함(S-SEC-10): ADD COLUMN으로 더해도
-- mookko:phase expand

ALTER TABLE __SCHEMA__.profiles ADD COLUMN wrapped_key bytea;

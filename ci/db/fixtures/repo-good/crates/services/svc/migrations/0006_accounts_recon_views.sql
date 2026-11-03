-- mookko:phase expand
-- 대사 계정(svc_recon)이 읽을 보기(S-SEC-9, E-DB-15). `accounts_recon`만 RECON_VIEWS에 적음.
-- `accounts_contact`는 개인 등급 `email`을 쓰는 보기 — 대사에 주면 적용 시험이 잡아야 함(시험이 일부러 줌).

SET LOCAL lock_timeout = '3s';

CREATE VIEW __SCHEMA__.accounts_recon AS
    SELECT account_id, state, created_at FROM __SCHEMA__.accounts;

CREATE VIEW __SCHEMA__.accounts_contact AS
    SELECT account_id FROM __SCHEMA__.accounts WHERE email IS NOT NULL;

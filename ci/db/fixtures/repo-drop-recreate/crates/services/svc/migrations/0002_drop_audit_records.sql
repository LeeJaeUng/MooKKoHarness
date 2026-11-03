-- mookko:phase contract
SET LOCAL lock_timeout = '3s';
DROP TABLE __SCHEMA__.audit_records;
DROP TABLE IF EXISTS __SCHEMA__.old_ledger;

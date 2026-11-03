-- mookko:phase expand
CREATE TABLE __SCHEMA__.audit_records (
    record_id uuid NOT NULL,
    CONSTRAINT audit_records_pkey PRIMARY KEY (record_id)
);
CREATE TABLE IF NOT EXISTS __SCHEMA__.old_ledger (
    entry_id uuid NOT NULL,
    CONSTRAINT old_ledger_pkey PRIMARY KEY (entry_id)
);

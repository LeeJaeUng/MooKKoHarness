-- mookko:phase expand
CREATE TABLE __SCHEMA__.audit_records (
    record_id uuid NOT NULL,
    CONSTRAINT audit_records_pkey PRIMARY KEY (record_id)
);

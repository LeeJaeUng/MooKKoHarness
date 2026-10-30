-- expect: (없음)
-- mookko:phase expand
CREATE TABLE __SCHEMA__.audit_chain_head (
    id integer NOT NULL,
    seq bigint NOT NULL,
    row_hash bytea NOT NULL,
    CONSTRAINT audit_chain_head_pkey PRIMARY KEY (id),
    CONSTRAINT audit_chain_head_one CHECK (id = 1)
);
GRANT SELECT, UPDATE ON __SCHEMA__.audit_chain_head TO svc_app;

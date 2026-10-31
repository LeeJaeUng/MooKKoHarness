-- mookko:phase expand

CREATE FUNCTION __SCHEMA__.reject_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'append-only table %', TG_TABLE_NAME USING ERRCODE = '42501';
END
$$;

CREATE TABLE __SCHEMA__.accounts (
    account_id uuid NOT NULL,
    email text NOT NULL,
    email_bidx bytea NOT NULL,
    email_bidx_kid text NOT NULL,
    state text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT accounts_pkey PRIMARY KEY (account_id),
    CONSTRAINT accounts_email_bidx_key UNIQUE (email_bidx),
    CONSTRAINT accounts_email_bidx_len CHECK (octet_length(email_bidx) = 32),
    CONSTRAINT accounts_email_bidx_kid_shape CHECK (email_bidx_kid ~ '^[A-Za-z0-9_-]{1,32}$'),
    CONSTRAINT accounts_state CHECK (state IN ('active', 'closed'))
);

CREATE INDEX accounts_created ON __SCHEMA__.accounts (created_at);

CREATE TABLE __SCHEMA__.ledger_entries (
    entry_id uuid NOT NULL,
    account_id uuid NOT NULL,
    amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    idempotency_key text NOT NULL CHECK (char_length(idempotency_key) <= 128),
    occurred_at timestamptz NOT NULL,
    CONSTRAINT ledger_entries_pkey PRIMARY KEY (occurred_at, entry_id),
    CONSTRAINT ledger_entries_idempotency UNIQUE (idempotency_key, occurred_at)
) PARTITION BY RANGE (occurred_at);


CREATE TRIGGER ledger_entries_append_only
BEFORE UPDATE OR DELETE ON __SCHEMA__.ledger_entries
FOR EACH ROW EXECUTE FUNCTION __SCHEMA__.reject_change();

CREATE TRIGGER ledger_entries_no_truncate
BEFORE TRUNCATE ON __SCHEMA__.ledger_entries
FOR EACH STATEMENT EXECUTE FUNCTION __SCHEMA__.reject_change();

GRANT USAGE ON SCHEMA __SCHEMA__ TO svc_app, svc_ro;
GRANT SELECT, INSERT, UPDATE ON __SCHEMA__.accounts TO svc_app;
GRANT SELECT, INSERT ON __SCHEMA__.ledger_entries TO svc_app;
GRANT SELECT ON __SCHEMA__.accounts, __SCHEMA__.ledger_entries TO svc_ro;

-- mookko:phase expand

CREATE TABLE __SCHEMA__.row_keys (
    subject_id uuid NOT NULL,
    purpose text NOT NULL,
    wrapped_key bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT row_keys_pkey PRIMARY KEY (subject_id, purpose),
    CONSTRAINT row_keys_purpose_shape CHECK (purpose ~ '^[a-z0-9._/-]{1,128}$')
);

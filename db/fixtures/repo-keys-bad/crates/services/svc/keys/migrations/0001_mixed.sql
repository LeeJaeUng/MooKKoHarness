-- 잡아야 함(S-SEC-10): 키 DB에 키 표가 아닌 표, wrapped_key 형식이 bytea가 아님
-- mookko:phase expand

CREATE TABLE __SCHEMA__.row_keys (
    subject_id uuid NOT NULL,
    purpose text NOT NULL,
    wrapped_key text NOT NULL,
    CONSTRAINT row_keys_pkey PRIMARY KEY (subject_id, purpose)
);

CREATE TABLE __SCHEMA__.notes (
    note_id uuid NOT NULL,
    body text NOT NULL,
    CONSTRAINT notes_pkey PRIMARY KEY (note_id)
);

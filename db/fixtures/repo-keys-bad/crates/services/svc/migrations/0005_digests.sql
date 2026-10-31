-- 설계서 대조(data_classes.py S-SEC-10): bytea + key 낱말은 설계서 보호 `해시`이거나 `이름 예외`여야 함
-- mookko:phase expand

CREATE TABLE __SCHEMA__.digests (
    digest_id uuid NOT NULL,
    session_key bytea NOT NULL,
    blob_key bytea NOT NULL,
    verify_key bytea NOT NULL,
    CONSTRAINT digests_pkey PRIMARY KEY (digest_id)
);

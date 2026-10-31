-- 잡아야 함(S-SEC-10): `wrapped_key`가 아닌 이름의 키 재료. 키 ID·판(`key_id`·`kek_version`)은 통과
-- mookko:phase expand

CREATE TABLE __SCHEMA__.vaults (
    vault_id uuid NOT NULL,
    dek bytea NOT NULL,
    row_key bytea NOT NULL,
    data_key text NOT NULL,
    wrapped_dek bytea NOT NULL,
    key_id text NOT NULL,
    kek_version integer NOT NULL,
    CONSTRAINT vaults_pkey PRIMARY KEY (vault_id)
);

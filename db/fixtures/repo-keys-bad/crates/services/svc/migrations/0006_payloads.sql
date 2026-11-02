-- 설계서 대조(data_classes.py S-SEC-10, QA 낮음 11-02): 이름에 key가 없는 bytea도 설계서 보호가 `암호`·`참조`면 잡음
-- mookko:phase expand

CREATE TABLE __SCHEMA__.payloads (
    payload_id uuid NOT NULL,
    payload bytea NOT NULL,
    chain_sha256 bytea NOT NULL,
    CONSTRAINT payloads_pkey PRIMARY KEY (payload_id)
);

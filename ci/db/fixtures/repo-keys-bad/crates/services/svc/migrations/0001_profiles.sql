-- 잡아야 함(S-SEC-10): 감싼 행 키를 서비스 DB에 둠(백업에 남아 키 파기가 안 됨)
-- mookko:phase expand

CREATE TABLE __SCHEMA__.profiles (
    profile_id uuid NOT NULL,
    nickname text NOT NULL,
    profile_wrapped_key bytea NOT NULL,
    CONSTRAINT profiles_pkey PRIMARY KEY (profile_id)
);

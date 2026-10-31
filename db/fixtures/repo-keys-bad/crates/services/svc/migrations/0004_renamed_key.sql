-- 잡아야 함(S-SEC-10): 이름 바꾸기로 키 재료 이름을 만듦(같은 파일에서 만든 표라 S-MIG-4는 아님)
-- mookko:phase expand

CREATE TABLE __SCHEMA__.blobs (
    blob_id uuid NOT NULL,
    payload bytea NOT NULL,
    CONSTRAINT blobs_pkey PRIMARY KEY (blob_id)
);

ALTER TABLE __SCHEMA__.blobs RENAME COLUMN payload TO subject_key;

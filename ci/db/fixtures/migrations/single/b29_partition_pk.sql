-- expect: S-PART-1
-- mookko:phase expand
CREATE TABLE __SCHEMA__.events (
    seq bigint GENERATED ALWAYS AS IDENTITY,
    at timestamptz NOT NULL,
    CONSTRAINT events_pkey PRIMARY KEY (seq),
    CONSTRAINT events_seq_key UNIQUE (seq, at)
) PARTITION BY RANGE (at);

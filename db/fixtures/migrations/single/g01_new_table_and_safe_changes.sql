-- expect: (없음)
-- mookko:phase expand
SET LOCAL lock_timeout = '2s';

-- 새 테이블은 같은 파일에서 바로 색인·제약을 걸어도 됨(비어 있음).
CREATE TABLE __SCHEMA__.items (
    item_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    label text NOT NULL CHECK (char_length(label) <= 80),
    price_minor bigint NOT NULL,
    price_currency char(3) NOT NULL,
    meta jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_hidden boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT items_pkey PRIMARY KEY (item_id)
);
CREATE INDEX items_owner ON __SCHEMA__.items (owner_id, created_at);
ALTER TABLE __SCHEMA__.items ADD CONSTRAINT items_label_key UNIQUE (label);

-- 기존 테이블: 상수·now() 기본값 열, NOT VALID 제약.
ALTER TABLE __SCHEMA__.old_items ADD COLUMN seen_at timestamptz DEFAULT now();
ALTER TABLE __SCHEMA__.old_items ADD COLUMN tier text NOT NULL DEFAULT 'basic';
ALTER TABLE __SCHEMA__.old_items ADD CONSTRAINT old_items_tier CHECK (tier IN ('basic', 'plus')) NOT VALID;

-- 문자열·함수 본문 안의 낱말은 문장으로 읽지 않음.
CREATE FUNCTION __SCHEMA__.touch() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    UPDATE __SCHEMA__.old_items SET seen_at = now() WHERE false; -- SELECT * FROM x; DROP TABLE y;
    RETURN NEW;
END
$body$;
COMMENT ON TABLE __SCHEMA__.items IS 'SELECT * FROM nowhere; DROP TABLE x';

CREATE VIEW __SCHEMA__.item_counts AS
SELECT i.owner_id, count(*) AS n
FROM __SCHEMA__.items i
JOIN __SCHEMA__.old_items o ON o.owner_id = i.owner_id
GROUP BY i.owner_id;

INSERT INTO __SCHEMA__.items (item_id, owner_id, label, price_minor, price_currency)
SELECT g, g, 'x', 0, 'KRW' FROM unnest(ARRAY[]::uuid[]) AS g
ON CONFLICT (item_id) DO NOTHING;

GRANT USAGE ON SCHEMA __SCHEMA__ TO svc_app, svc_read;
GRANT SELECT, INSERT, UPDATE ON __SCHEMA__.items TO svc_app;
GRANT SELECT ON __SCHEMA__.items, __SCHEMA__.item_counts TO svc_read;

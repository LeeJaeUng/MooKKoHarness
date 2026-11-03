-- 표본: 0002 contract가 지우는 열·표를 코드가 아직 부르면 S-MIG-13.
-- mookko:phase expand
CREATE TABLE __SCHEMA__.items (
    item_id uuid NOT NULL,
    old_note text,
    CONSTRAINT items_pkey PRIMARY KEY (item_id)
);
CREATE TABLE __SCHEMA__.olds (
    old_id uuid NOT NULL,
    CONSTRAINT olds_pkey PRIMARY KEY (old_id)
);

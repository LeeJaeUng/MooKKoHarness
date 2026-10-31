-- mookko:phase expand
SET LOCAL lock_timeout = '3s';

CREATE TABLE __SCHEMA__.items (
    item_id uuid NOT NULL,
    kind text,
    CONSTRAINT items_pkey PRIMARY KEY (item_id)
);

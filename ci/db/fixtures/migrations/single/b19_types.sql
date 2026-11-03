-- expect: S-TYPE-1, S-TYPE-2, S-TYPE-3, S-TYPE-5
-- mookko:phase expand
CREATE TABLE __SCHEMA__.items (
    item_id uuid PRIMARY KEY,
    seen_at timestamp NOT NULL,
    label varchar(10),
    meta json,
    n serial
);

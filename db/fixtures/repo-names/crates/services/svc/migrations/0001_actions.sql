-- 표본(S-NAME-2): staff_id는 등록 글과 같은 CHECK, created_by는 다른 CHECK(잡아야 함), approved_by는 넓히기에서 NOT VALID로 맞춤(통과)
-- mookko:phase expand

CREATE TABLE __SCHEMA__.actions (
    action_id uuid NOT NULL,
    staff_id text NOT NULL,
    created_by text NOT NULL,
    approved_by text,
    CONSTRAINT actions_pkey PRIMARY KEY (action_id),
    CONSTRAINT actions_staff_id CHECK (char_length(staff_id) BETWEEN 1 AND 200 AND staff_id ~ '^[!-~]([ -~]*[!-~])?$'),
    CONSTRAINT actions_created_by CHECK (char_length(created_by) <= 64)
);

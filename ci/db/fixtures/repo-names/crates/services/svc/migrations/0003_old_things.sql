-- 표본(S-NAME-2): made_by는 CHECK가 없지만 0004 contract가 표를 지우므로 안 봄, published_by는 uuid라 안 봄
-- mookko:phase expand

CREATE TABLE __SCHEMA__.old_things (
    thing_id uuid NOT NULL,
    made_by text NOT NULL,
    CONSTRAINT old_things_pkey PRIMARY KEY (thing_id)
);

CREATE TABLE __SCHEMA__.posts (
    post_id uuid NOT NULL,
    published_by uuid NOT NULL,
    CONSTRAINT posts_pkey PRIMARY KEY (post_id)
);

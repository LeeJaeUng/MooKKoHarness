-- 잡아야 함: ONLY 부모 제약, VOLATILE 함수, 없는 함수. 통과: IMMUTABLE+search_path, 뒤에서 고친 함수
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';

ALTER TABLE ONLY __SCHEMA__.events ADD CONSTRAINT events_tags_only CHECK (tags IS NULL OR cardinality(tags) <= 8) NOT VALID;
ALTER TABLE __SCHEMA__.events ADD CONSTRAINT events_tags_ok CHECK (tags IS NULL OR __SCHEMA__.tags_ok(tags)) NOT VALID;
ALTER TABLE __SCHEMA__.events ADD CONSTRAINT events_tags_volatile CHECK (__SCHEMA__.tags_volatile(tags)) NOT VALID;
ALTER TABLE __SCHEMA__.events ADD CONSTRAINT events_tags_missing CHECK (__SCHEMA__.tags_nowhere(tags)) NOT VALID;
ALTER TABLE __SCHEMA__.events ADD CONSTRAINT events_tags_later CHECK (__SCHEMA__.tags_fixed_later(tags)) NOT VALID;

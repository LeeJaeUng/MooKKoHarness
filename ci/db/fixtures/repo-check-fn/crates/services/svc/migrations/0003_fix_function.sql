-- 커밋한 함수는 뒤 이관에서 search_path를 붙여 고침(통과)
-- mookko:phase expand
SET LOCAL lock_timeout = '3s';

ALTER FUNCTION __SCHEMA__.tags_fixed_later(text[]) SET search_path = pg_catalog;

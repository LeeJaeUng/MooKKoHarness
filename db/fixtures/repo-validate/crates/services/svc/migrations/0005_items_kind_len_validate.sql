-- mookko:phase migrate
-- mookko:validate-deploy same 옛 판은 kind를 'a'·'b'로만 씀(8자 넘는 값을 쓸 수 없음)
SET LOCAL lock_timeout = '3s';

ALTER TABLE __SCHEMA__.items VALIDATE CONSTRAINT items_kind_len;

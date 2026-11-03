-- mookko:phase migrate
-- 표본(S-MIG-4가 잡아야 함): 바로 앞 NOT VALID를 VALIDATE만 하는데 배포·근거가 없음.
SET LOCAL lock_timeout = '3s';

ALTER TABLE __SCHEMA__.items VALIDATE CONSTRAINT items_kind;

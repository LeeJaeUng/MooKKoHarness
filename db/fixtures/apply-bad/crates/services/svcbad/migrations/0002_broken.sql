-- 적용 시험이 잡아야 할 것: 없는 열을 쓰는 문장(문법·의미 오류)
-- mookko:phase expand
CREATE INDEX audit_events_missing ON __SCHEMA__.audit_events (no_such_column);

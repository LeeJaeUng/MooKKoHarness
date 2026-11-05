-- 적용 시험이 잡아야 할 것: 다음 파일(0002)이 실패하면 S-MIG-8 한 줄과 "뒤 검사는 건너뜀" 한 줄만 나와야 함 —
-- 반쯤 적용된 스키마는 보지 않으므로 여기의 numeric(S-TYPE)·막기 트리거 없음(S-MONEY-2)은 잡히지 않아야 함.
-- mookko:phase expand
CREATE TABLE __SCHEMA__.audit_events (event_id uuid PRIMARY KEY, amount numeric(10, 2));

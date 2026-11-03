-- mookko:phase expand
-- 표본(S-PART-3이 잡아야 함): 파티션 부모 둘. `events`는 코드가 엔진에 적지 않았고(블록 주석 안에만), `visits`는 적었다.
-- `visits_202611`은 일반 표인데 엔진 달 파티션 이름과 겹친다.

SET LOCAL lock_timeout = '3s';

CREATE TABLE __SCHEMA__.events (
    event_id uuid NOT NULL,
    at timestamptz NOT NULL,
    CONSTRAINT events_pkey PRIMARY KEY (at, event_id)
) PARTITION BY RANGE (at);

CREATE TABLE __SCHEMA__.visits (
    visit_id uuid NOT NULL,
    day date NOT NULL,
    CONSTRAINT visits_pkey PRIMARY KEY (day, visit_id)
) PARTITION BY RANGE (day);

CREATE TABLE __SCHEMA__.visits_202611 (
    visit_id uuid NOT NULL,
    CONSTRAINT visits_202611_pkey PRIMARY KEY (visit_id)
);

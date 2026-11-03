-- mookko:phase expand
-- 표본(S-SEC-9가 잡아야 함): 개인 등급 열이 있는 표 셋. `people`·`visits`는 열지 않았고(괜찮음), `notes`는 표째 열었다(걸림).

SET LOCAL lock_timeout = '3s';

CREATE TABLE __SCHEMA__.people (
    person_id uuid NOT NULL,
    email text NOT NULL,
    CONSTRAINT people_pkey PRIMARY KEY (person_id)
);

CREATE TABLE __SCHEMA__.notes (
    note_id uuid NOT NULL,
    body text NOT NULL,
    CONSTRAINT notes_pkey PRIMARY KEY (note_id)
);

CREATE TABLE __SCHEMA__.visits (
    visit_id uuid NOT NULL,
    ip_hash bytea NOT NULL,
    CONSTRAINT visits_pkey PRIMARY KEY (visit_id)
);

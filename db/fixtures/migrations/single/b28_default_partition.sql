-- expect: S-PART-2
-- mookko:phase expand
CREATE TABLE __SCHEMA__.events (event_id uuid NOT NULL, at timestamptz NOT NULL, PRIMARY KEY (at, event_id)) PARTITION BY RANGE (at);
CREATE TABLE __SCHEMA__.events_default PARTITION OF __SCHEMA__.events DEFAULT;

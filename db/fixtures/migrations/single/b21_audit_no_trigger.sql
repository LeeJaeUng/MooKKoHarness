-- expect: S-MONEY-2
-- mookko:phase expand
CREATE TABLE __SCHEMA__.audit_events (event_id uuid PRIMARY KEY, at timestamptz NOT NULL);

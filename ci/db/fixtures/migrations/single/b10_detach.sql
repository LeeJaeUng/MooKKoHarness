-- expect: S-MIG-2i
-- mookko:phase contract
SET LOCAL lock_timeout = '3s';
ALTER TABLE __SCHEMA__.old_events DETACH PARTITION __SCHEMA__.old_events_2026_01;

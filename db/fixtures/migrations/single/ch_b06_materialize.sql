-- expect: S-CH-2
-- mookko:phase migrate
ALTER TABLE mookko_logs.raw MATERIALIZE COLUMN HostId;

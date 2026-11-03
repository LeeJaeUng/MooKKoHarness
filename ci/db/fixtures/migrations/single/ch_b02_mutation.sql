-- expect: S-CH-2
-- mookko:phase migrate
ALTER TABLE mookko_logs.raw DELETE WHERE Ts < now();
OPTIMIZE TABLE mookko_logs.raw FINAL;

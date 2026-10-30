-- expect: S-CH-1, S-CH-5, S-CH-7
-- mookko:phase expand
CREATE TABLE mookko_logs.raw (Ts DateTime, Body String) ENGINE = MergeTree ORDER BY Ts;

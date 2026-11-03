-- expect: S-CH-6
-- mookko:phase expand
CREATE SETTINGS PROFILE IF NOT EXISTS mookko_logs_query SETTINGS readonly = 2, max_execution_time = 10 MAX 10, max_memory_usage = 1073741824, max_rows_to_read = 100000000 MAX 100000000, max_result_rows = 10000 CONST;

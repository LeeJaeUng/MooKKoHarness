-- mookko:transaction off
-- mookko:phase expand
CREATE INDEX CONCURRENTLY IF NOT EXISTS audit_log_x ON __SCHEMA__.audit_log (log_id);

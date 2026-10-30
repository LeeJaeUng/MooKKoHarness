-- mookko:transaction off
-- mookko:phase expand
CREATE INDEX CONCURRENTLY IF NOT EXISTS accounts_closed ON __SCHEMA__.accounts (closed_at) WHERE closed_at IS NOT NULL;

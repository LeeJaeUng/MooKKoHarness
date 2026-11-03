-- mookko:transaction off
-- mookko:phase expand
-- mookko:expected 30
CREATE INDEX CONCURRENTLY IF NOT EXISTS accounts_closed ON __SCHEMA__.accounts (closed_at) WHERE closed_at IS NOT NULL;

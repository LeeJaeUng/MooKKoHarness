-- expect: S-MIG-5
-- mookko:phase expand
SET lock_timeout = '3s';
CREATE TABLE __SCHEMA__.items (item_id uuid PRIMARY KEY);

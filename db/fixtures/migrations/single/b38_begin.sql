-- expect: S-MIG-6
-- mookko:phase expand
BEGIN;
CREATE TABLE __SCHEMA__.items (item_id uuid PRIMARY KEY);
COMMIT;

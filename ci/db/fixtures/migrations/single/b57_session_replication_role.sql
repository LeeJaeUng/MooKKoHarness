-- expect: S-MONEY-2
-- mookko:phase migrate
SET LOCAL session_replication_role = replica;
INSERT INTO __SCHEMA__.items (item_id) VALUES ('00000000-0000-7000-8000-000000000000');

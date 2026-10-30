-- expect: S-MIG-7
-- mookko:phase migrate
INSERT INTO __SCHEMA__.new_items (item_id) SELECT item_id FROM __SCHEMA__.old_items;

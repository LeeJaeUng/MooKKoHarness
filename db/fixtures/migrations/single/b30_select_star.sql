-- expect: S-Q-2
-- mookko:phase expand
CREATE VIEW __SCHEMA__.items_view AS SELECT * FROM __SCHEMA__.old_items;
CREATE VIEW __SCHEMA__.items_view2 AS SELECT i.* FROM __SCHEMA__.old_items i;

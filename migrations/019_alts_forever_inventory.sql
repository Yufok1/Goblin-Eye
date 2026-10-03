CREATE TABLE character_inventory_observations (
    snapshot_id INTEGER NOT NULL REFERENCES character_snapshots(id),
    location TEXT NOT NULL CHECK(location IN ('bag','bank','mail')),
    item_id INTEGER NOT NULL CHECK(item_id > 0),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    PRIMARY KEY(snapshot_id, location, item_id)
);
CREATE INDEX character_inventory_item_lookup ON character_inventory_observations(item_id);

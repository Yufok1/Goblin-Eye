ALTER TABLE snapshots ADD COLUMN source_complete_claim INTEGER;
CREATE TABLE auction_rows (
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    ordinal INTEGER NOT NULL,
    item_id INTEGER NOT NULL CHECK(item_id > 0),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    buyout_copper INTEGER NOT NULL CHECK(buyout_copper >= 0),
    bid_copper INTEGER NOT NULL CHECK(bid_copper >= 0),
    time_left_code INTEGER NOT NULL CHECK(time_left_code BETWEEN 0 AND 4),
    PRIMARY KEY(snapshot_id, ordinal)
);
CREATE INDEX idx_auction_rows_item ON auction_rows(item_id,snapshot_id);

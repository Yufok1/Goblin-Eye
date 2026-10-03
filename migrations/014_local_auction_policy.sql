CREATE TABLE auction_policy (
    id INTEGER PRIMARY KEY CHECK(id=1),
    reset_at TEXT NOT NULL,
    market_key TEXT NOT NULL DEFAULT 'wow-forever',
    faction TEXT NOT NULL DEFAULT 'horde',
    ruleset TEXT NOT NULL DEFAULT 'pvp'
);
CREATE TABLE auction_reset_baselines (
    path TEXT NOT NULL,
    raw_market TEXT NOT NULL,
    item_key TEXT NOT NULL,
    digest TEXT NOT NULL,
    PRIMARY KEY(path,raw_market,item_key)
);

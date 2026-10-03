-- Preserve historical reset values, but remove faction/ruleset defaults for new rows.
ALTER TABLE auction_policy RENAME TO auction_policy_legacy;
CREATE TABLE auction_policy (
    id INTEGER PRIMARY KEY CHECK(id=1),
    reset_at TEXT NOT NULL,
    market_key TEXT NOT NULL DEFAULT 'wow-forever',
    faction TEXT NOT NULL DEFAULT 'unknown',
    ruleset TEXT NOT NULL DEFAULT 'unknown'
);
INSERT INTO auction_policy SELECT * FROM auction_policy_legacy;
DROP TABLE auction_policy_legacy;

CREATE TABLE local_market_profile (
    id INTEGER PRIMARY KEY CHECK(id=1),
    faction TEXT NOT NULL DEFAULT 'unknown',
    ruleset TEXT NOT NULL DEFAULT 'unknown',
    region TEXT NOT NULL DEFAULT 'unknown',
    realm TEXT NOT NULL DEFAULT 'unknown',
    legacy_unverified INTEGER NOT NULL DEFAULT 0
);
INSERT INTO local_market_profile(id,legacy_unverified)
SELECT 1, EXISTS(SELECT 1 FROM markets WHERE market_key='wow-forever');

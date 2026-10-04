-- Keep IDs and all linked evidence intact. Earlier releases assigned this
-- pooled market a faction/ruleset without checking the scan identity.
-- Fresh imports must use a separate market, rather than deleting the history
-- or retroactively claiming it belongs to the new selected profile.
UPDATE markets SET market_key='wow-forever-legacy',
    name='WoW Forever (legacy identity unverified)',
    faction='unknown', ruleset='unknown', region='unknown', is_verified=0
WHERE market_key='wow-forever'
  AND EXISTS(SELECT 1 FROM local_market_profile WHERE legacy_unverified=1);

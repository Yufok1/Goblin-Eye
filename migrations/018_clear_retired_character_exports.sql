-- Retire the old manually imported character records while preserving the
-- provider-neutral tables and companion notes for a new saved-file source.
UPDATE companion_entries SET character_snapshot_id=NULL WHERE character_snapshot_id IS NOT NULL;
DELETE FROM character_item_observations;
DELETE FROM character_snapshots;

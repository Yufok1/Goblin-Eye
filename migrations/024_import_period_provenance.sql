-- Preserve configured import labels without treating them as source observation phases.
ALTER TABLE market_captures ADD COLUMN import_economic_period TEXT NOT NULL DEFAULT 'unknown';
UPDATE market_captures SET import_economic_period=economic_period;
UPDATE market_captures SET economic_period='unknown'
 WHERE source_id IN (SELECT id FROM sources WHERE source_key='ahledger');
UPDATE markets SET content_phase='Forever; observation phase unknown'
 WHERE source_id IN (SELECT id FROM sources WHERE source_key='ahledger');
UPDATE item_observations SET content_phase='Forever; observation phase unknown'
 WHERE source_id IN (SELECT id FROM sources WHERE source_key='ahledger');

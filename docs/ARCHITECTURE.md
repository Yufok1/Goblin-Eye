# Architecture

This share edition starts empty. Each database holds one local market profile;
faction, ruleset, region and realm default to unknown and are only established by
explicit configuration or source-reported scan fields. Local observations and
all six public Forever markets retain separate provenance. Generic auction
imports and bulk history recovery remain disabled.

## Evidence pipeline

Adapters decode a documented or directly inspected source into normalized SQLite records. They never generate conclusions or fill absent fields. Source records retain retrieval time, build or content phase when known, confidence, evidence kind, and a raw reference.

The Auctionator adapter watches the account-wide SavedVariables file. It uses the addon’s inspected version-8 structure: `m` is the latest observed minimum unit price, `l` and `h` are daily bounds for the observed low price, and `a` is the daily available quantity. The raw database key is retained because gear variants can use composite keys.

## Agent boundary

The HTTP API and MCP server expose evidence. Codex or Claude can search records, follow item relationships, compare timestamps, and request explicit arithmetic. Any interpretation belongs to the live agent conversation and is not persisted as authoritative advice.

The companion layer keeps optional player goals and session context in separate `companion_entries` tables. Entries state whether they are player reports, sourced claims, or agent inferences; status changes have an audit trail. `goblin-eye companion-mcp` exposes bounded writes to these tables while the original `goblin-eye mcp` command remains read-only. Neither path embeds a model or provider routing. The local dashboard and JSON API expose the same entries. See [Companion](COMPANION.md).

## Interfaces

The local HTTP server binds to `127.0.0.1` by default:

- `/api/health`
- `/api/market-observations`
- `/api/evidence?q=...`
- `/api/items/{id}`
- `/api/farming`
- `/api/sources`
- `/api/next-data`
- `/api/characters` and `/api/characters/{snapshot_id}`
  expose Alts Forever v2 observations with character capture/import timestamps,
  explicit gear slots, quantity-bearing bag/bank/mail items, raw layout and coverage.
  An independent dashboard file watcher imports WoW-written saves; literal Lua is
  parsed without execution. Identity is scoped to saved-file/account context and
  full name; realm/race/build are unknown. Latest character selection orders by
  source capture time, not import order. Inventory rows are separate from auction
  evidence and are removed by an explicit personal-data reset.
- `/api/documents` and `/api/documents/{id}?offset=0&limit=100000` (byte chunks)
- `/api/scans?market_key=...` (retained snapshot IDs and timestamps)
- `/api/scan-history?item_id=...&market_key=...&start=...&end=...&period=...`
- `/api/price-history?item_id=...&market_key=...` (paged immutable observations)
- `/api/price-reference` (explicit source, market, item, period and time window)
- `/api/compare-scans?item_id=...&market_key=...&before_id=...&after_id=...`
- `/api/assertions?entity_type=items&entity_key=...`
- `/api/world-search?query=Arugal&zone=Silverpine` (active source assertions)
- `/api/acquisition-search?item_id=2592&method=drop&max_level=26&rank=0`
- `/api/acquisition?item_id=...` also accepts the acquisition search filters
- `/api/scan-summary?sort_by=listed_units` (latest local scan, optional snapshot ID)
- `/api/history-coverage?market_key=wow-forever` (sources, phases and date coverage)

The discovery routes share MCP schemas and bounds. `research_queries.py` filters
active source assertions before pagination, preserves acquisition provenance and
adds separately sourced quality. `world_labels.py` contains reviewed addon map
and rank display metadata with source hashes; it does not assert current spawns.
No scan or research data is rewritten by these query improvements.

The stdio MCP server exposes the same evidence through read-only tools. It has no embedded model and serves the compatible client that launches it; a paid subscription is not required by Goblin Eye.

The item graph also exposes `/api/items`, `/api/recipes/{fact_id}`, `/api/research-datasets`, `/api/acquisition`, `/api/world/{entity_type}/{entity_id}`, and `/api/market-depth`. Acquisition and listing endpoints are paginated. Market depth requires an explicit local market key; source identity is not merged by assumption.

The local HTTP listener uses exclusive address binding on Windows. A second server on the same port fails visibly instead of sharing the port with a stale instance.

`/api/market-depth` accepts `snapshot_id` for historical local scans. Query commands
and MCP use read-only database connections and require a matching schema; run
`goblin-eye init` explicitly to migrate. The server's import workers remain writers.
Static requests resolve only within the web roots.

Immutable `market_captures` and `market_price_points` retain source identity,
timestamps/precision, period/build, raw-document links and recovery labels. Daily
compatibility tables remain available but are not the history authority. Local
listing rows remain linked to their original snapshots. `evidence_assertions`
and conflict records preserve generic alternatives; selected legacy projections
use a visible trust/recency policy.

## Data limitations

An Auctionator scan is market evidence, not completed-sale evidence. Its aggregate SavedVariables history cannot answer stack-size or individual-listing questions. Disappearance can represent a sale, cancellation, or expiry. A separate permitted dataset is required for more detailed claims.


## Agent response boundary

`agent_responses.py` provides compact projections for MCP/CLI research calls.
Provenance is deduplicated into an evidence map, discovery pages have continuation
offsets and a 32 KB payload budget, and money fields include computed denomination
strings. Item research defaults to a summary; existing HTTP item and UI contracts
remain full detail. Oversized nonpaged responses fail with recovery instructions.
`get_acquisition_evidence` and `get_scan_provenance` expose focused original evidence.
No storage schema or source data is modified by these projections.

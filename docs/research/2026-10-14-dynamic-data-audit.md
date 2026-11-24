# Goblin Eye: dynamic evidence audit

Reviewed October 14, 2026. Source health was refreshed through `get_source_health` at 21:26:31 UTC. All seven active research datasets were inspected through `get_research_datasets(active=true, limit=20)`; `next_offset` was null. Companion context was queried; no saved goals or notes were returned.

## Finding

Goblin Eye has a useful foundation for evolving research. Its main item, recipe, acquisition, world and travel data comes from imported evidence, rather than a hand-written universal loot or BiS list. Dataset revisions, hashes, provenance, source limitations and previous imports are preserved.

It is not yet a complete dynamic discovery system. Some source selection and game metadata are embedded in code; several adapters currently reject newer installed data; and a retained active dataset is not necessarily current or suitable for a new report. A comprehensive Forever boss-mechanics and class raid-pack feature does not exist in the reviewed research backend.

This was a read-only architecture and evidence audit. It covered the operating contract, configuration, ingestion/discovery/watchers, dataset schema, query/provenance paths, MCP tools, dashboard research surface, current source health and relevant existing regression tests. It is not a line-by-line certification of every file, an exhaustive catalog of every constant, a security audit, or independent validation of every imported game claim. Pre-existing working changes were preserved. No live evidence import, addon installation or runtime change was performed for this audit.

## What already supports changing discoveries

- `research_datasets` identifies revisions by source, dataset key and hash, preserves source version/build/phase/retrieval time/limitations, and permits only one active revision per source and dataset key. See [dataset schema](D:/End-Game/ended_game/codex_playground/Goblin-Eye/migrations/005_recipe_evidence.sql:2).
- Installed catalogs are checked on dashboard startup and periodically for file changes. Successful signatures are remembered only after import; failed sources retry, and Forever Guide components are handled independently. See [static watcher](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/ingestion/static_watcher.py:23) and [Forever Guide watcher](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/ingestion/foreverguide.py:213).
- Hashing and transactional revision activation allow new imports without discarding historical evidence. Strict parsers treat Lua as data and reject unfamiliar structures instead of executing addon source or inventing missing IDs.
- Acquisition records distinguish historical Classic baselines, bundled references and Forever community associations. Item variants/builds and conflicting assertions remain separate. Observed talents are character captures, not a complete talent-theory or simulation database.
- Original source documents and evidence references make later review possible. A cached file is still a provider assertion; a recent import does not independently verify its content.
- Automatic ingestion runs in the dashboard process. MCP queries read the database and do not themselves start or prove the health of those background workers. See [operating guide](D:/End-Game/ended_game/codex_playground/Goblin-Eye/docs/OPERATING_GUIDE.md:35).

A static catalog file is not inherently a stagnant design: a replaceable, versioned source snapshot is valuable. The remaining distinction is between refreshing known inputs, discovering new resources, reviewing changed formats, and deciding whether evidence is eligible for a report. Those are separate jobs.

## Findings that need attention

| Finding | Evidence and consequence | Recommended direction |
| --- | --- | --- |
| Official discovery is fixed in code | [official.py:15](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/ingestion/official.py:15) lists six URLs. The watcher refetches those pages; it does not discover new announcements, hotfix posts or guides. | Configurable source registry, supported announcement/feed discovery, and a review queue for new source types. Keep discovery separate from promoting claims. |
| One official fetch failure aborts that refresh cycle | [official.py:37](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/ingestion/official.py:37) downloads all pages before its database transaction. Earlier cached documents remain, but successfully downloaded pages in that failed cycle are not committed. | Per-document health, revision history and independent refresh results. |
| Zone-name metadata is frozen in Python | [world_labels.py:3](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/world_labels.py:3) contains reviewed older map names and a September 28 provenance record. [Textual zone matching](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/research_queries.py:62) uses that dictionary. New imported areas may remain unnamed or fail ordinary named-zone filtering. | Import versioned map/area labels and aliases; preserve namespace distinctions and unknowns. |
| Active does not mean fresh | [World queries](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/item_graph.py:188) select active datasets without an automatic source-error/freshness eligibility gate. Common [provenance fields](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/research_queries.py:14) do not attach source `last_error`. Separate health queries currently matter. | Preserve last good evidence, but expose source failure and section-specific readiness alongside it. A report must say when newer input failed. |
| Global freshness is auction-specific | [services.py:476](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/services.py:476) explicitly scopes `is_stale` to newest auction evidence. Public market activity cannot establish fresh local listings, equipment, mechanics or loot. | Freshness and compatibility by source, claim and report section, not one green status for everything. |
| Parser-version hashing is inconsistent | [Acquisition](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/ingestion/foreverguide.py:148) and [profession](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/ingestion/foreverguide_professions.py:193) fingerprints use selected content files without a parser revision; [Mapzeroth](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/ingestion/mapzeroth.py:167) also lacks an explicit parser revision. Other adapters already include one. Identical bytes can skip new parsing semantics after a code update. TOC-only changes can also leave older dataset version metadata for acquisition/professions. | Standardize content identity, parser/schema version, provider release metadata and last checked time as distinct fields. |
| Change detection begins with file metadata | Watcher signatures use path, modification time and size before invoking content-hashing adapters. A same-size replacement that preserves timestamps could be missed. | Periodic content reconciliation in addition to fast metadata checks. This is an edge case, not evidence that ordinary updates are missed. |
| Some advertised providers are placeholders | [Booty Bay Broker and TheWoWDB](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/ingestion/providers.py:21) deliberately refuse imports pending access/schema/provenance review. Installed AtlasLoot data is reported as unconnected. | Show connected, installed-but-unconnected, gated and proposed sources distinctly. A provider name is not an integration. |
| Raid reporting needs additional evidence types | Reviewed migrations, ingestion adapters, MCP surface and dashboard have no dedicated encounter-phase/mechanic model or class raid-pack exporter. Existing world/loot records do not establish a complete encounter guide. | Add a sourced encounter/class model and a separate report renderer only after agreeing implementation scope. |

Compatibility allowlists, slot enums, field mappings and parser guards are not equivalent to hardcoded item rankings. Keep those contracts explicit and reviewed. Removing validation to make an update appear successful would sacrifice provenance.

## Current import failures

These were present in both health checks this turn. They are actual integration blockers, not hypothetical future risks.

| Source | Current error | Basis and retained evidence |
| --- | --- | --- |
| `local-alts-forever-export` | `Unreviewed Alts Forever version in AltsForever_Camelot.toc; export extension not installed` | [Installer contract](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/ingestion/item_export_setup.py:18) accepts exactly 0.10.0; installed manifests previously inspected in this conversation report 0.12.0. The error does not prove all character imports stopped, or that every existing numeric capture is missing. |
| `foreverguide-dungeons` | `Forever Guide dungeon provenance changed` | [Provenance check](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/ingestion/foreverguide_dungeons.py:39) expects older literal header text. The installed package has a changed attribution header. Active dataset 21 remains version 1.26.1, imported October 9. Review the new attribution and schema before adapting. |
| `foreverguide-items` | `Unexpected content after item catalog` | The [item parser](D:/End-Game/ended_game/codex_playground/Goblin-Eye/src/goblin_eye/ingestion/foreverguide_items.py:62) expects the supported catalog layout. The installed file contains additional `ns.CAT_NAMES[id]` assignments. Active dataset 22 remains version 1.26.1, imported October 9. |

Other active revisions include Forever Guide acquisition/professions 1.35.1, QuestieDB 1.0.6, Mapzeroth 0.8.0, and ProfessionDB 1.9.1. Acquisition/profession/world/travel datasets were imported October 14; ProfessionDB October 9. A newer profession revision does not make the separately failing item or dungeon components current. Dataset ages are not proof of incorrect facts, but they must remain visible.

## Raid evidence boundary

[Blizzard's current roadmap article](https://news.blizzard.com/en-us/article/24303862/world-of-warcraft-forever-whats-next-panel-recap), reopened this turn, states November 4, 2026 launch and December 9 raid unlocks. The roadmap image linked there was inspected earlier in this conversation: the first wave groups Barrow Deeps (10), Hyjal Summit (20), and Onyxia's Lair (40). It does not establish an order between those three. Future seasonal entries do not justify inventing unrevealed names or exact dates.

Earlier targeted local checks found no imported raid label for those three and no current Forever Onyxia drop associations in the selected `forever_drop` scope. The 17 epic Onyxia `drop` associations reviewed were Classic baselines. Those checks do not establish exhaustive global absence: the broad mixed association list had unreviewed pages. Nothing here promotes historical Onyxia mechanics, loot rates or another expansion's Hyjal into verified Forever facts.

## Recommended sequence

1. Review and repair the three compatibility failures; retain provenance checks and add focused regression coverage for the reviewed new formats.
2. Standardize dataset/parser identity and expose per-source failures, applicable build/edition and per-section readiness in query results.
3. Add configurable source discovery and independently refreshed documents; replace the fixed zone-name registry with sourced metadata.
4. Research actual Forever encounter, class/spec, loot and theorycraft sources. Validate access, coverage, upstream lineage and update behavior before calling an integration complete.
5. Model claims and their dependencies, then generate class packs from eligible evidence. Changed claims should invalidate affected sections and exports; an offline ZIP remains a dated snapshot until regenerated.

The companion Deep Research prompt specifies this research and design work. It does not authorize implementation, installation or automated distribution.

## Verification

Ran 31 existing tests across `test_auto_ingestion`, `test_item_properties`, `test_research_coverage`, and `test_game_boundary`: all passed in 49.898 seconds. These exercise change/retry behavior, independent catalog errors, revision retention, item/stat/build provenance, paging, capture distinctions and the research/gameplay boundary using fixtures and temporary databases. They do not certify the incompatible installed addon revisions or verify upcoming raid mechanics. No new tests were added for this read-only audit.

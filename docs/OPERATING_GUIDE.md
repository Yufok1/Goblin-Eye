# Everyday research

Start the Windows launcher as described in START-HERE.md at the package root. All paths are
relative to your extracted folder; the database is data/goblin-eye.db and the
default dashboard is http://127.0.0.1:8765/. The clean package contains no saved
player evidence. Its local faction, ruleset, region and realm stay unknown until
you configure them or a source reports them.

For companion work, read get_companion_context, then query fresh evidence.

Launchers keep writable profiles, temp files and tool/model caches under
`data/runtime` on the installation's non-system drive. They reject C: for
runtime storage; installed binaries and Windows dependencies may still be read
from C:. The chat bridge has its own agent sign-ins; see IN_GAME_CHAT.md.

| Question | Query sequence |
| --- | --- |
| Available evidence | get_economic_summary, then get_source_health |
| Character or gear | list_characters, then get_character_snapshot |
| Quest route | list_characters, intended get_character_snapshot, then get_character_active_quests; page next_offset and follow quest IDs into world evidence |
| Item uses | search_items, get_item_research, get_recipe_evidence |
| Acquisition | search_acquisition_sources or get_item_acquisition, then get_world_entity |
| NPCs and locations | search_world_entities with zone/level/rank filters |
| Asking prices | get_market_depth for an explicit market and source |
| Supply | get_scan_summary (listed supply, not completed sales) |
| History | get_history_coverage, then dated price or scan queries |
| Source disagreements | get_fact_assertions and source-specific recipe evidence |

Keep observations separate from interpretation. Report source capture dates,
confidence and missing fields. Public quotes are regional community references;
local addon prices are personal observations. Listing disappearance does not
prove a sale. Follow compact pages' next_offset and shared provenance.

Alts Forever observations update when WoW saves after /reload or logout.
Active quest titles, objective counters and explicit turn-in readiness come from
the Alts extension. `saved_location` is a separate login/save observation with
normalized 0–1 coordinates and a UI map ID, never a live position. Missing or
partial captures must not be treated as an empty quest log. Completion history
remains available separately through `get_character_quests`.
`get_source_health` returns a bounded summary; use its section counts and
follow-ups to page sources, markets, files, adapters and public references.
Equipment slots are explicit; bags have quantities. Bank/mail/recipes need
their corresponding windows opened. Missing data is unknown and an empty
mail object alone does not prove coverage. Exported full names must not be
split into character and realm. The optional Alts extension records client
realm/race/build and timestamped character-sheet/quest observations; the base
save omits those fields. Refresh source health after a new save.

The dashboard automatically imports installed Auctionator, AHledger, Alts
Forever, ProfessionDB, Forever Guide, QuestieDB, and Mapzeroth when enabled and
discovered. Static catalogs load on startup and are checked for file changes
every 60 seconds. Blizzard reference pages and public AHledger refresh on the
configured external interval (30 minutes by default). The optional modified WoWAI chat addon is bundled; these data addons
are installed separately by the player. Keep the dashboard running for automatic ingestion; MCP queries
read its database and do not start background import workers.

Background importers queue database writes per local database file within the
dashboard process. Large imports can make another import wait; dashboard and MCP
reads continue to use committed evidence while it runs. Source-error logging uses
the same writer queue. Downloads and source parsing happen outside write scopes.

Discovery checks common Forever client locations independently of other addons.
For a different install location, set the corresponding addon directory in
`questiedb_paths`, `mapzeroth_paths`, `professiondb_paths`, or `foreverguide_paths`;
saved-file path overrides remain available for personal observation addons.
Imports retry after failures without deleting existing evidence. Forever Guide
catalogs fail independently; name-only quest placeholders stay in cached source
coverage rather than becoming fabricated numeric quest IDs. Source health
includes active world entity, travel node and travel edge counts.

For CLI fallback, open PowerShell in the extracted folder and use the bundled
`python\python.exe -m goblin_eye` followed by `characters`, `sources`,
`observations`, `companion`, or `research TOOL --arguments-file FILE.json`.
The local API supplies /api/health, /api/characters, /api/sources, /api/items,
/api/world-search, /api/acquisition-search, /api/scan-summary, and history.

Generic auction imports and bulk recovery remain disabled. Public AHledger
syncing and supported local addon imports remain separate. A new copy has no
personal reset cutoff; this is not proof that addon observations are recent.
Explicit reset commands delete evidence and can pause collection; they are
maintenance tools, not required setup steps. Do not run them to troubleshoot
an empty view. Back up your own data before upgrades.

Connect an MCP client using AGENT_SETUP.md in this docs folder. The optional WoWAI chat interface uses a separately configured agent CLI;
there is no embedded AI model or game automation. See IN_GAME_CHAT.md. Every in-game action and decision remains yours.

## Equipment and item properties

Use the existing `get_character_snapshot` and `get_item_research` tools. Forever Guide ItemCatalogData.lua, GearData.lua and ItemStatsData.lua import through its existing watcher independently of WoWAI. Character results include explicit slot names, observed item names/links/quality, per-item property variants and shared provenance. Item research keeps properties in compact and full replies. Slots absent from the save remain not_recorded; an explicitly nil slot is recorded_empty. Ranged is separate from Off Hand.

The catalogs can disagree on quality, levels or stats; their assertions stay separate with build and Classic fallback labels. Spell power, spell damage and school damage stay distinct unless equivalence is verified. Duplicate stat keys remain arrays in stats_raw and are omitted from normalized stats rather than summed. Base stats do not resolve bonus IDs, random suffixes or enchants from modern links. The optional Alts extension supplies timestamped client item and character-sheet observations; unsupported or uncaptured fields remain unknown. Do not call an item an upgrade, BiS or a Shadow Wrath item by its name/color alone.

For exact full-link observations, permanent enchants, Questie completion and report preflight, follow [Reliable gear research](GEAR_RESEARCH.md). These imports use the existing data addons and are independent of WoWAI.

Research coverage: narrow broad searches before paging. Follow next_offset for each chosen scope; report unsearched pages and missing metadata explicitly. Never claim no candidates from a partial page. Return fewer verified targets rather than filling a requested count with unsupported upgrades. Quest level filters use quest difficulty, not acceptance level; verify required level and prerequisites separately. Baseline dungeon drops remain classic_baseline, not verified Forever loot. Historical character observations are limited to evidence known at snapshot import; static catalogs remain current enrichment.

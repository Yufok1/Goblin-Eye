# Everyday research

Start the Windows launcher as described in START-HERE.md at the package root. All paths are
relative to your extracted folder; the database is data/goblin-eye.db and the
default dashboard is http://127.0.0.1:8765/. The clean package contains no saved
player evidence. Its local faction, ruleset, region and realm stay unknown until
you configure them or a source reports them.

For companion work, read get_companion_context, then query fresh evidence.

| Question | Query sequence |
| --- | --- |
| Available evidence | get_economic_summary, then get_source_health |
| Character or gear | list_characters, then get_character_snapshot |
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
Equipment slots are explicit; bags have quantities. Bank/mail/recipes need
their corresponding windows opened. Missing data is unknown and an empty
mail object alone does not prove coverage. Exported full names must not be
split into character and realm. Realm, race and build are not exported by this
inspected format. Refresh source health after a new save.

The dashboard automatically imports installed Auctionator, AHledger, Alts
Forever, ProfessionDB, Forever Guide, QuestieDB, and Mapzeroth when enabled and
discovered. Static catalogs load on startup and are checked for file changes
every 60 seconds. Blizzard reference pages and public AHledger refresh on the
configured external interval (30 minutes by default). No third-party game addon
is bundled. Keep the dashboard running for automatic ingestion; MCP queries
read its database and do not start background import workers.

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

Connect an MCP client using AGENT_SETUP.md in this docs folder. There is no embedded chat model
or game automation. Every in-game action and decision remains yours.

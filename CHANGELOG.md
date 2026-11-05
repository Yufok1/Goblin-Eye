# Changelog

## Unreleased

- Discover the Forever live client before beta, respect explicit source paths, and
  keep chat MCP connections on the configured database. Review Alts Forever 1.0.1
  for the existing observation export.
- Queue background database writes without blocking committed-evidence reads;
  import QuestieDB quest requirements and sourced area-to-map mappings.
- Accept reviewed Forever Guide catalog corrections and updated dungeon
  provenance while preserving mixed builds and Classic baselines.
- Add the 28-prompt in-game research library, complete cached model catalogs,
  automatic model discovery/retries, and clear Antigravity approval failures.

- Observe exact equipped and encountered item variants through Alts Forever, with bounded capture and backups; keep WoWAI as conversation only.
- Import ProfessionDB applied enchant stats, Questie completion caches and all supported Forever Guide tooltip stat keys.
- Add report preflight, paged equipment/inventory/datasets/evidence, and sourced dungeon membership filters.
- Keep oversized MCP responses usable and explicitly distinguish missing observations from absent game content.

- Accept AHledger public price tables with either eight legacy fields or nine current fields. Preserve the additional daily sales estimate in market history with explicit provider attribution; unknown estimates remain unknown.

- Restore Goblin Eye grimoire theme and optional private speech runtime (no voice assets distributed).
- Populate existing character/item tools from installed Forever Guide item catalogs, keeping stat variants, conflicts, source builds and Classic fallbacks visible.
- Preserve explicit equipment slots and separate unavailable character totals from base item stats. No WoWAI equipment requests or gameplay access.

- Support ProfessionDB 1.9 borrowed required-skill annotations and additional
  metadata catalogs without executing Lua. Retain borrowed origins in recipe
  evidence; cache availability/location catalogs without asserting their contents
  as verified Forever facts.
- Prevent old saved prompts and interrupted accepted requests from executing
  automatically when the WoWAI bridge restarts. Preserve history with a stopped
  notice; continuing requires a new player message.
- Add Stop below Send and `/wow-ai stop` (`cancel` is an alias). Cancel running
  agent subprocess trees or queued work in the selected chat, preserve drafts,
  reject late replies and retain cancellation across UI reloads.

## 0.2.0 â€” 2026-10-04

- Include the optional MIT-licensed WoWAI companion with full replies, expandable
  tool/evidence cards, copyable source links and improved rendering/publishing.
- Add Kilo headless sessions, per-chat settings and supported dynamic model
  catalogs, plus a single-bridge lock to prevent competing state writers.
- Add local Windows Desktop speech for summaries/full replies with Play/Stop,
  voice settings, formatting cleanup and stable older-reply lookup.
- Exclude Warcraft recordings, character-cloning presets and neural voice assets.
- Provide guided client/account/agent setup and local read-only MCP connections
  for Codex, Claude and Kilo. No realm, faction or model is hardcoded.
- Package the companion source/launchers with bundled Python and the dashboard;
  Node and an agent CLI are needed only for optional in-game chat.
- Verify clean mock-client installation, relocation, privacy and fresh ZIP setup.
  Existing core databases/scans are preserved; no reset is needed.

## 0.1.1 — 2026-10-04

- Support Auctionator 340 normalized realm and regional ruleset keys, alongside
  legacy realm/faction keys. Explicitly selected regional storage takes priority
  over old realm data; unknown identity is never inferred from a realm label.
- Read both serialized CBOR and literal Lua price tables without executing Lua.
- Expose saved-file import errors in MCP/API source health and the dashboard,
  including failures that happen before a source has ever imported successfully.
- Back off unchanged Auctionator failures for at least 60 seconds, while changed
  files or market settings retry immediately; successful imports clear the error.
- Preserve existing databases and scans; no schema migration or reset is needed.

## 0.1.0 — 2026-10-03

Initial public source preparation for the Windows edition.

- Local auction, character, inventory, recipe and world research dashboard.
- One configurable local market profile per database; faction, ruleset, region
  and realm default to unknown and are never inferred from a realm name.
- Imports skip unrelated saved realms/factions rather than aborting the selected
  market. An unset AHledger profile uses its newest eligible saved scan.
- Non-destructive upgrades preserve earlier pooled scans under an unverified
  legacy market while allowing fresh scans into the selected market.
- Read-only MCP plus optional bounded companion goals and notes.
- A vendored, hash-pinned Python runtime, so neither the release ZIP nor a GitHub
  source download requires the player to install Python.
- Updated the bundled interpreter to official CPython 3.13.16 and verified the
  archive against its published SHA-256; runtime paths follow the pinned ABI.
- Automatic imports for supported saved files, ProfessionDB, Forever Guide,
  QuestieDB and Mapzeroth; scheduled public AHledger and Blizzard reference refreshes.
- Fixed Forever Guide's name-only dungeon quest handling and isolated catalog errors.
- Source health shows world/travel counts and known unconnected data addons.
- CurseForge-first setup instructions and a launcher that selects its own source.
- Portable, deterministic Windows ZIP builder and clean-install verifier.
- Public defaults no longer claim the recipient has confirmed the original player's market.

Current limitations: Windows end-user support; local market identity stays
unknown until configured or source-reported; no GatherLite or AtlasLoot importer;
no embedded AI model or gameplay automation.

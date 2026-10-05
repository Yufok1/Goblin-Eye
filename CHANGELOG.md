# Changelog

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

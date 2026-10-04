# Changelog

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

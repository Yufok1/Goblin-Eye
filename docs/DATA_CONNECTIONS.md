# Data connection audit, 2026-10-03

All implemented addon importers now run automatically while the dashboard is
running. No separate static import command is required. Data is read from disk;
WoW must still save personal observations after /reload, logout or normal exit.

| Connection | Automatic behavior | Imported scope |
| --- | --- | --- |
| Alts Forever | Startup; saved file changes every 3 seconds by default | Exported character, equipment, bag, bank, mail, profession and learned recipe observations |
| Auctionator | Startup; saved file changes every 3 seconds | Aggregate price evidence, not individual auction rows |
| Local AHledger | Startup; saved file changes every 3 seconds | Saved auction listing scans |
| Public AHledger | Startup; every 30 minutes by default | Separate regional community price and item references |
| ProfessionDB | Startup; installed file changes every 60 seconds | 2,511 active recipe assertions in the audited revision |
| Forever Guide acquisition | Startup; installed file changes every 60 seconds | 323,513 acquisition links and 20,754 entity facts in the audited revision |
| Forever Guide professions | Startup; installed file changes every 60 seconds | 2,495 recipes, 549 acquisition links and 5,015 entity facts |
| Forever Guide dungeons | Startup; installed file changes every 60 seconds | 137 loot/reward links and 131 entity facts |
| QuestieDB | Startup; installed file changes every 60 seconds | 16,788 NPC/object records, 112,011 spawn coordinate points and 23,418 waypoint points |
| Mapzeroth | Startup; installed file changes every 60 seconds | 922 travel nodes and 352 authored connections |
| Blizzard official pages | Startup; every 30 minutes by default | Six source documents cached verbatim, without generating game-rule assertions |

Counts describe active source revisions, overlap between providers is preserved,
and static source assertions do not prove current in-game availability.

## Fixed population failures

- ProfessionDB 1.9 added `LoadBorrowed` annotations and separate metadata files.
  Recipe imports accept the inspected literal format, retain borrowed skill
  origins (374 Vanilla skill annotations in the inspected 1.9 package), and cache
  the additional files as source documents. Hidden-recipe flags and emulator-sourced
  NPC acquisition catalogs are not imported as verified Forever assertions.
- QuestieDB and Mapzeroth previously had import commands but no automatic workers.
- Blizzard publication caching previously required a separate sync command.
- ProfessionDB, Forever Guide and local AHledger discovery could depend on another
  addon being present. Discovery now checks supported client locations directly.
- Forever Guide 1.18.4 introduced eleven name-only quest placeholders. The dungeon
  parser previously rejected them and prevented the whole catalog from importing.
  They are now counted and retained in cached source, without fabricated quest IDs.
- A dungeon import failure previously marked the working acquisition/profession
  catalogs as failed too. Each catalog now has independent change detection,
  failure reporting and retries.
- Source health previously omitted world/travel counts. Those counts now appear,
  along with installed research addons that have no importer and provider stubs.

## Data that still does not populate

- **GatherLite** is installed, including its static Forever gathering locations.
  Goblin Eye has no GatherLite importer. Herb/ore locations in that catalog and
  its personal gathering observations therefore are not imported.
- **AtlasLoot Continued** is installed with item-source and related modules.
  Goblin Eye has no AtlasLoot importer; those catalogs are not independently
  imported. Some information may overlap with existing providers.
- **Booty Bay Broker** and **TheWoWDB** are schema-gated connector stubs. They
  remain unavailable until permitted access, schemas and provenance are verified.
- **QuestieDB coverage** currently includes NPCs, objects, spawns and waypoints;
  this is not a full quest/objective import or the player's active quest log.
- **Mapzeroth coverage** is the static travel graph; it does not import the
  character's flight discoveries, hearthstone or runtime ability calculations.
- **Alts Forever categories** only populate if that addon has exported them.
  Opening bank/mail/profession windows in game may be needed for capture; the
  resulting saves import automatically. Missing coverage remains unknown.
- **GuildRoster and addon UI/configuration files** have no companion research
  importer. WoWAI slots transport chat replies and are not research datasets.
- Arbitrary JSON/CSV auction bulk imports remain disabled maintenance formats;
  they are not installed addon connections and are not automatically ingested.

Seven regression checks cover discovery without prerequisite addons,
configuration compatibility, unchanged/changed files, failed import retries,
first-failure visibility, independent Forever Guide catalogs, and synthetic
quest handling. The dashboard TypeScript build also passed. The live dashboard
was restarted and all nine importer workers were observed running; all eleven
implemented source records had no import error following automatic startup.

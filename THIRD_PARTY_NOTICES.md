# Third-party sources and attribution

The MIT license in LICENSE applies to project-authored Goblin Eye software.
WoW and its game data belong to their respective rights holders. Goblin Eye is
an independent project and is not affiliated with or endorsed by Blizzard.

Goblin Eye reads these separately installed or publicly available sources:

| Source | Project |
| --- | --- |
| Alts Forever | https://www.curseforge.com/wow/addons/alts-forever |
| Auctionator | https://www.curseforge.com/wow/addons/auctionator |
| AHledger addon and public API | https://ahledger.com/developers |
| LibProfessionDB | https://www.curseforge.com/wow/addons/libprofessiondb |
| Forever Guide | https://www.curseforge.com/wow/addons/forever-guide |
| Questie / QuestieDB | https://github.com/Questie/QuestieDB |
| Mapzeroth | https://www.curseforge.com/wow/addons/mapzeroth |
| Official Blizzard publications | https://worldofwarcraft.blizzard.com/ |

Their addon code, catalogs and cached documents retain their own ownership and
terms. They are not bundled in the repository or Windows ZIP. Imports occur
locally from the user's installation or the documented public endpoints.

The small zone-name and NPC-rank reference tables in
`src/goblin_eye/world_labels.py` retain their Forever Guide source version,
file reference, retrieval timestamp and hash. These game display labels are
reference metadata, not a live spawn database or part of the project's code license.

## Bundled runtime

The repository and the Windows ZIP include a **vendored Python runtime** in
`python/`, so that a player can run Goblin Eye without installing an
interpreter. It is the official CPython Windows embeddable distribution:

| Component | Version | License |
| --- | --- | --- |
| CPython embeddable (amd64) | 3.13.16 | PSF-2.0 — https://docs.python.org/3/license.html |

It is unmodified apart from `python313._pth`, which is rewritten to add this
project's `src` directory, and `scripts/python_runtime.json`, which records the
pinned upstream URL and SHA-256. `python/.goblin-eye-python.json` records the
installed version and hash. `scripts/fetch_python.py --check` verifies that
record, and `scripts/build_release.py` refuses to package a runtime that does not
match the pin. No other Python distribution, package, or binary is bundled.

## Development dependency

TypeScript 5.9.2 (Apache-2.0) is a development dependency used to compile the
project's dashboard. It is pinned in package-lock.json and is not shipped as a
runtime dependency. The GitHub addon sources listed above are installed
separately by the player.

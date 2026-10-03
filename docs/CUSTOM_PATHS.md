# Point Goblin Eye at a custom WoW installation

Use this when supported addons are installed somewhere discovery does not check.
The current version checks `_classic_beta_` inside these WoW installation roots:

- `C:\Program Files (x86)\World of Warcraft`
- `C:\Program Files\World of Warcraft`
- `C:\Games\World of Warcraft`
- `D:\World of Warcraft`
- `D:\Games\World of Warcraft`

1. Start Goblin Eye once so it creates `config.json`, then stop it with Ctrl+C
   in its console. Open that file in Notepad.
2. Find the relevant setting below. Replace its empty `[]` with the full path in
   quotes, inside square brackets. Use forward slashes in the path.
3. Save the file and launch `Start-Goblin-Eye.cmd` again.

| Setting in config.json | Point it at |
| --- | --- |
| `alts_forever_paths` | The account-level `WTF/Account/YOUR_ACCOUNT/SavedVariables/AltsForever.lua` file |
| `auctionator_paths` | The account-level `SavedVariables/Auctionator.lua` file |
| `ahledger_scan_paths` | The account-level `SavedVariables/AHledger.lua` file |
| `professiondb_paths` | The `Interface/AddOns/ProfessionDB` folder |
| `foreverguide_paths` | The `Interface/AddOns/ForeverGuide` folder |
| `questiedb_paths` | The `Interface/AddOns/QuestieDB` folder |
| `mapzeroth_paths` | The `Interface/AddOns/Mapzeroth` folder |

For example, replace the existing `"questiedb_paths": [],` line with:

```json
"questiedb_paths": ["E:/Games/World of Warcraft/_classic_beta_/Interface/AddOns/QuestieDB"],
```

For Alts Forever, use the actual account folder name you see in File Explorer:

```json
"alts_forever_paths": ["E:/Games/World of Warcraft/_classic_beta_/WTF/Account/YOUR_ACCOUNT/SavedVariables/AltsForever.lua"],
```

These are individual settings inside the existing JSON object, not replacement
contents for the whole file. Preserve the commas between settings. Personal
SavedVariables files appear after the relevant addon has run and WoW has saved
with /reload, logout or normal exit. Once the paths are configured, imports
continue automatically.

Advanced options: individual `auto_*` switches control automatic imports;
`economic_period` labels new captures, for example `forever-beta`. Changing that
label does not relabel past observations or establish a region/ruleset match.

## Manual addon installation

The normal setup uses CurseForge, as described in START-HERE.md. Use these
steps only if you choose to install an addon manually or need a missing dependency.

Close WoW, download the compatible addon release ZIP, and extract its addon
folders directly into `World of Warcraft/_classic_beta_/Interface/AddOns`.
Each addon folder should contain its `.toc` file directly, without an extra
wrapper folder. Restart WoW and enable the addon on the character screen.

The supported folders are `AltsForever`, `Auctionator`, `AHledger`,
`ProfessionDB`, `ForeverGuide`, `Questie`, `QuestieDB`, and `Mapzeroth`.

If QuestieDB is missing after installing the compatible Questie release, check
the [QuestieDB stable release](https://github.com/Questie/QuestieDB/releases/latest).
Expand **Assets**, download **QuestieDB-all.zip**, and extract its `QuestieDB`
folder into AddOns alongside `Questie`. Use the ready-made addon archive rather
than GitHub's **Source code** download. The installed database should contain
`QuestieDB_Forever.toc`.

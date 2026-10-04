# Goblin Eye — start here

Goblin Eye puts your saved auction scans, character information, recipes, item
sources and world locations in a local browser dashboard. This Windows share
edition includes the fixes from October 3, 2026.

**You can use the dashboard without an AI subscription.** Optional AI setup comes
after the dashboard works. Your local auction workspace is recorded as
**unknown** faction, ruleset, region and realm until a source reports them or you set them in
`config.json`; the dashboard works for any Forever server. Public regional
markets are shown separately.

## 1. Start Goblin Eye

1. **Right-click the Goblin Eye ZIP → Extract All.** Choose a writable location,
   such as Documents. Open the extracted `Goblin-Eye` folder. Extract the whole
   ZIP: the `python` folder inside it is the bundled runtime.
2. **Double-click `Start-Goblin-Eye.cmd`.** It prepares everything on the first
   run, then opens the dashboard. Keep its console window open while using it.
3. If the browser does not open, visit **http://127.0.0.1:8765/**. If the page opens
   before startup finishes, refresh it once the console says the server is running.

**There is nothing to install.** Python is bundled in the ZIP, so you do not need
to install Python, Node.js, npm, pip packages, an API key, or an AI subscription,
and you do not need administrator access. Your database starts empty.

Use the launcher **inside the extracted folder every time**. From PowerShell in
that folder, the equivalent is:

```powershell
.\Start-Goblin-Eye.cmd
```

The bare command `goblin-eye serve` can point to a different, previously installed
copy even when your terminal is in the correct folder. The included launcher
always selects this copy.

Goblin Eye stays in its own folder, outside WoW's AddOns folder.

## 2. Install the addons through CurseForge

1. Open **CurseForge** and select **World of Warcraft**.
2. Select your **Forever** game installation. Check that you are managing the
   same installation you actually play; the supported beta folder is `_classic_beta_`.
3. Search for and install the addons listed below. Select releases marked
   **Forever / 1.60.1** when a project supports several WoW editions.
4. Let CurseForge install the required dependencies and keep them installed.
   Restart WoW and check that the addons are enabled on the character screen.

Already installed them through CurseForge? Keep that setup and continue to
**Get your first data** below. There is no need to download addon ZIPs manually.

| Addon / download | What Goblin Eye reads | What you need to do |
| --- | --- | --- |
| [Alts Forever](https://www.curseforge.com/wow/addons/alts-forever) | Character, equipment, bags, professions, and recorded bank/mail/known recipes | Log in. Open the bank, mailbox and each profession window to capture those categories. |
| [Auctionator](https://www.curseforge.com/wow/addons/auctionator) | Your saved aggregate auction prices | At the auction house, use Auctionator's **Full Scan** and let it finish. |
| [AHledger](https://www.curseforge.com/wow/addons/ahledger) | Your saved individual auction listings | Open the auction house and let its scan finish; `/ahl status` shows its scan status. |
| [LibProfessionDB](https://www.curseforge.com/wow/addons/libprofessiondb) — folder name `ProfessionDB` | Recipe ingredients and profession requirements | Install the Forever-compatible package. No in-game scan needed for its static catalog. |
| [Forever Guide](https://www.curseforge.com/wow/addons/forever-guide) | Static item sources, recipes, dungeon loot and verified reward references | Install it. Its supported catalogs import automatically. |
| [Questie](https://www.curseforge.com/wow/addons/questie) | In-game quest helper; Goblin Eye reads its separate QuestieDB dependency below | Install the Forever-compatible release and keep its required dependency installed. |
| QuestieDB — Questie's required database | NPC/object spawn and waypoint references | Keep the database installed with the Forever-compatible Questie package. It is listed separately here because this is the data Goblin Eye imports. |
| [Mapzeroth](https://www.curseforge.com/wow/addons/mapzeroth) | Static travel nodes and connections | Install the **Forever** release. No in-game scan needed for the imported travel catalog. |

CurseForge may also install helper libraries; leave those in place. The Goblin
Eye ZIP contains the desktop application, while CurseForge manages the addons.
For a missing dependency or a manual installation, see the
[advanced installation notes](docs/CUSTOM_PATHS.md#manual-addon-installation).

You can start with **Alts Forever + AHledger + Auctionator** for your character
and market data, then add the static research addons. The dashboard opens even
without any addons installed.

## 3. Get your first data

1. Leave Goblin Eye running and log into the character you want to research.
2. Open your bags and profession windows. Visit your bank/mailbox if you want
   their contents recorded too.
3. At the auction house, finish your Auctionator and AHledger scans.
4. Type **`/reload` in WoW** to write the saved addon data to disk. Logging out
   or exiting WoW normally also saves it.
5. Return to Goblin Eye and check **Source health**, **Characters**, and
   **Saved scan overview**. Personal saves are checked every few seconds;
   static addon catalogs are checked every minute. Large first imports can
   take longer.

**There are no manual import commands to run.** Keep the dashboard running;
supported saved files and changed static catalogs import automatically.
The public AHledger reference feed and official Blizzard pages also refresh
automatically when internet access is available.

Goblin Eye reads the local AHledger save directly. You do not need AHledger's
separate upload/sync app or an AHledger account for this local import.

An import timestamp shows when Goblin Eye read a file; the scan/capture timestamp
shows when the game data was recorded. Missing bank, mail or recipe data usually
means that category has not been captured yet.

## Choose your market

Use a separate extracted Goblin Eye folder for each realm/faction you play.
AHledger's newest eligible saved scan identifies an unset local profile;
scans from other realms/factions are skipped. Auctionator can identify a single
saved realm/faction, but cannot choose between several without that profile.

To select a market yourself, stop Goblin Eye, edit these fields in `config.json`,
and restart it. For example, replace `Your realm name` with your actual realm:

```json
"local_realm": "Your realm name",
"local_faction": "alliance",
"local_region": "eu",
"local_ruleset": "normal"
```

Faction choices are `horde`, `alliance`, `neutral`, or `unknown`; ruleset choices
are `normal`, `pvp`, `rp`, or `unknown`. Leave region/ruleset `unknown` if you do
not know them. The realm name alone does not establish either. Once scans have
established a profile, changing it to a different market requires a separate
copy with an empty database so the prices cannot be mixed.

Upgrades preserve older pooled scans under **WoW Forever (legacy identity
unverified)**. Select that market in History to inspect them separately.
Fresh scans continue in the current market; no reset or data deletion is needed.

## 4. Optional: use an AI

The dashboard works on its own. To let an AI query it directly, follow
[Connect your agent](docs/AGENT_SETUP.md) using a client that supports a
**local MCP connection**. Whether a free AI client supports this depends on
that client. A browser chat does not automatically gain access to your PC.

You can also copy sourced dashboard results into a free chat service and ask
questions about them. Goblin Eye supplies no model, account, credentials or
subscription. **WoWAI is not included or required.** `Start-Agent.cmd` is the
connection endpoint for an AI client; double-clicking it does not open a chat UI.

## What is not connected yet?

**GatherLite, AtlasLoot Continued and GuildRoster** can be installed for their
in-game features, but Goblin Eye currently has no importers for them. They are
not required for this setup. Booty Bay Broker and TheWoWDB connectors are also
unfinished. See [Data connections](docs/DATA_CONNECTIONS.md) for exact coverage.

QuestieDB imports static NPC/object locations, not your active quest log.
Mapzeroth imports its static graph, not your character's flight discoveries.
Goblin Eye does not control gameplay. Auction asking prices do not prove sales,
and static spawn references do not show live mob availability.

## If something goes wrong

| Symptom | What to do |
| --- | --- |
| `python\python.exe` is missing | Extract the **complete** ZIP. The `python` folder is the bundled runtime and must stay inside the Goblin Eye folder. See [Python is already included](INSTALL-PYTHON.md). |
| `Unknown configuration keys` after `goblin-eye serve` | Launch `Start-Goblin-Eye.cmd` from this extracted folder. An old global command may be selecting an older copy. Keep the new configuration keys. |
| Port already in use | Open http://127.0.0.1:8765/ first; Goblin Eye may already be running. Use one server at a time. |
| Character or scans are empty | Confirm the addons are enabled, finish the capture/scan, then `/reload` in WoW. Check Source health for an import error. |
| Questie data is missing | Confirm `QuestieDB` is installed alongside `Questie`, including its Forever `.toc` file. |
| Static data is missing | Check the Forever addon version, installation folder, and Source health. Allow the first import to finish. |
| WoW is installed in a custom location | Follow [Custom install paths](docs/CUSTOM_PATHS.md). Discovery currently checks common C: and D: locations for `_classic_beta_`. |
| You moved the extracted folder and it will not start | There is no environment to clean up any more. Put the whole folder back together, or extract the ZIP again somewhere writable, then run `Start-Goblin-Eye.cmd`. Keep `data` and `config.json` if you want your evidence. |
| Updating an existing copy | Extract the new ZIP separately. Stop Goblin Eye, back up your old `data` folder and `config.json`, then copy them into the new folder before launching it. |

Every friend gets their own database. Keep their data and settings separate.
For further details, see [Requirements](REQUIREMENTS.md) and the
[Operating guide](docs/OPERATING_GUIDE.md).

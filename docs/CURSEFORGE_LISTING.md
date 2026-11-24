# Goblin Eye

Goblin Eye brings your local WoW Forever research companion into the game:
chat with your configured AI, inspect research and evidence cards, browse the
bundled prompt library, choose models per chat, and optionally hear replies
through Windows speech. The companion's browser dashboard keeps your saved
character, auction, recipe and world-source evidence together.

**The complete Windows companion is required for the full setup.** This
CurseForge download installs the existing in-game interface. It does not bundle
an AI model or run the desktop backend inside WoW.

## Get started

1. Install this addon for **WoW Forever / 1.60.1**. Its in-game name is currently
   **WoW AI** and its folder is `WoWAI`; keep only one copy installed.
2. Get the matching **Goblin Eye complete Windows ZIP** from
   [GitHub releases](https://github.com/Yufok1/Goblin-Eye/releases). Extract it
   outside your AddOns folder and follow `START-HERE.md`.
3. For in-game chat, install **Node.js 22.2+** and a supported, configured agent
   CLI. Follow `docs/IN_GAME_CHAT.md` and run `Setup-WoWAI.cmd` to connect your
   client/account and create the reply-slot addons. Setup does not install the
   separately maintained data addons.
4. Fully restart WoW, enable **WoW AI** and its reply slots, start the dashboard
   and chat companion, then open `/wow-ai`.

Supported adapters include Codex, Claude Code and Kilo. Availability, accounts,
model access and any provider charges depend on your chosen client/provider.
The browser dashboard itself requires no AI subscription and includes Python.

## Your evidence, with sources

Goblin Eye imports saved observations from **Alts Forever, AHledger and
Auctionator**, plus supported static catalogs from **LibProfessionDB,
Forever Guide, QuestieDB and Mapzeroth**. Install those separately through
CurseForge as described in `START-HERE.md`. They are not bundled in this addon.
Use their normal capture/scan flows, then `/reload` or log out to save data.
Capture times and missing evidence stay explicit. Auction asking prices do
not establish completed sales, and static location data does not show live
availability.

## How the companion works

The existing WoWAI chat-strip transport carries conversation to the local
bridge; local reply-slot files carry responses back. Research reads saved addon
files and supported static catalogs. The player performs every game action:
Goblin Eye does not issue game inputs, read game process memory or automate
auctions. Your prompts and relevant retrieved evidence may be sent to your
selected AI provider. Local saves, chat histories, credentials and databases
are not part of the clean downloads.

Update the addon and desktop companion together, with the bridge stopped and
WoW closed. Rerun `Setup-WoWAI.cmd` after updates and fully restart WoW so its
reply and signal files are present. The bridge writes local transport files,
so CurseForge may report the addon as modified.

Goblin Eye includes a modified MIT-licensed
[WoWAI by chelinho139](https://github.com/chelinho139/wow-ai); attribution and
license notices are preserved. Independent project; not affiliated with or
endorsed by Blizzard.

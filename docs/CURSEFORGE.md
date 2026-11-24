# Goblin Eye on CurseForge

Goblin Eye keeps its existing in-game chat, research and evidence cards, prompt
library, model settings, map UI, optional Windows speech and browser dashboard.
The CurseForge ZIP contains the existing in-game addon. The complete Windows
download supplies its desktop companion, research database and AI bridge.

**Both downloads are needed for the full experience.** Installing the addon
alone does not start a backend, connect an AI, or supply auction/character data.
No AI model, subscription or player data is included in either clean package.
The dashboard itself needs no AI subscription. In-game AI chat needs Node.js
22.2+ and a supported agent CLI with its own configured account/provider.

## Installation

1. Download the matching **complete Windows edition** from
   [Goblin Eye releases](https://github.com/Yufok1/Goblin-Eye/releases).
   Extract the whole ZIP to a writable folder outside the game's AddOns folder.
   Run `Start-Goblin-Eye.cmd` and follow its `START-HERE.md`.
2. Install the Goblin Eye addon for **Forever / 1.60.1** through CurseForge
   once a release is published. For a local preview, extract the CurseForge
   ZIP into the client's `Interface/AddOns` folder. Its root is `WoWAI`;
   retain that name and use only one copy of WoWAI.
3. Follow `docs/IN_GAME_CHAT.md` in the Windows download. Install Node.js and
   your chosen agent CLI, then run `Setup-WoWAI.cmd`. Setup selects the client
   and account, creates local AI/MCP connections, installs the matching addon,
   and generates the reply-slot addons and signal files used by the existing
   no-reload chat transport. CurseForge installation alone does not create them.
4. Install the separately maintained data addons listed in `START-HERE.md`
   through CurseForge. Those addons and their catalogs are not bundled here.
5. Fully quit and restart WoW; enable **WoW AI** and its **WoW AI slot** addons.
   Run `Start-Goblin-Eye-Chat.cmd`, keep the dashboard running, and open
   `/wow-ai`. Capture and save addon observations as described in `START-HERE.md`.

The addon retains its existing `WoWAI` folder, `/wow-ai` command, saved-variable
names and bridge protocol. This preserves compatibility with the current setup.
Use matching desktop and addon releases: setup copies the desktop download's
addon into the game, so an older desktop download can replace a newer addon.

## Updates

Stop the chat bridge and close WoW before updating. Follow the Windows guide to
back up and carry forward your own `data` folder and `config.json`. Update the
desktop download and CurseForge addon to matching releases, rerun
`Setup-WoWAI.cmd`, then fully restart WoW and the companion. Setup recreates any
signal files removed by an addon update and preserves an existing reply Inbox.
CurseForge can report locally written transport files as modified. Never upload
the installed addon directory: its Inbox and generated reply slots can contain
private conversation data.

## Building the upload

From the repository root, with the existing development dependencies installed:

```powershell
node wow-ai/build-addon.js
.\python\python.exe scripts/build_curseforge.py
```

The output is `dist/Goblin-Eye-<version>-CurseForge.zip`, plus its checksum and
packaging validation report. The ZIP has a single `WoWAI` root with the matching
`WoWAI.toc`. It contains only the reviewed repository addon assets, these
instructions, and both MIT license notices. It contains no Python executable,
desktop launcher, local configuration, database, chat history or installed addon
files. The existing Windows builder remains `scripts/build_release.py`.

Packaging validation checks archive contents, privacy, the empty Inbox and TOC
references. It does not certify a live-game test or CurseForge approval.

## Publishing checklist

- Create a **Goblin Eye** World of Warcraft addon project, with the **Forever**
  flavor and **1.60.1** version. Use the project's MIT license and retain the
  WoWAI upstream attribution. The addon list currently displays **WoW AI**.
- Upload only the `-CurseForge.zip` as the addon file. Publish the matching
  complete Windows ZIP as a GitHub release; link that specific release in the
  CurseForge description. The current repository release link above is a
  destination, not a claim that a matching release is already published.
- Clearly disclose that the desktop companion, Node.js, configured agent CLI
  and separately installed data addons are needed for the full setup. Do not
  describe it as a standalone addon or promise that CurseForge installs them.
- Describe the existing chat-strip transport, local reply files and saved-addon
  research imports. Player prompts and retrieved evidence may be sent to their
  chosen AI provider. No game inputs or game-memory reads are performed.
- Add screenshots supplied by the author and release notes for the actual build.
  Submit the project/file for CurseForge review. A locally valid ZIP is not an
  approval guarantee. This builder does not create a listing or upload files.

CurseForge's [packaging and visibility guidance](https://support.curseforge.com/support/solutions/articles/9000196615-known-issues)
requires the addon folder/TOC layout and appropriate game-version tags.
An existing Forever [addon with a separate desktop companion](https://www.curseforge.com/wow/addons/thanessynclite)
shows this distribution arrangement; its listing does not establish approval
for Goblin Eye.

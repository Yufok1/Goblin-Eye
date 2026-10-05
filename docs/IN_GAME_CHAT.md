# Optional in-game chat

The complete Windows ZIP includes a modified [WoWAI](https://github.com/chelinho139/wow-ai)
addon and its local bridge. The dashboard and normal MCP connections still work
without it. WoWAI runs an installed agent CLI; it does not include an AI model or
subscription. Kilo can use whatever models your configured provider makes
available, including free models. Availability and provider limits can change.

## Install once

1. Start `Start-Goblin-Eye.cmd` and confirm the dashboard works.
2. Install [Node.js](https://nodejs.org/en/download) **22.2 or newer** and one
   supported agent CLI. Install/login instructions are in
   [WoWAI agents](../wow-ai/docs/AGENTS.md). No npm packages are required to run
   the bridge itself; npm dependencies are only for development tests.
3. Double-click **Setup-WoWAI.cmd**. Confirm the Forever client folder (the one
   containing `Wow*.exe` and `Interface`), account folder and default agent.
   When several accounts exist, setup requires you to select one.
4. From `Goblin-Eye-Chat`, start your chosen CLI once, log in if required, and
   accept its project/MCP trust prompt. Setup creates local connections for
   **Codex, Claude Code and Kilo**. Other adapters need their client's MCP setup
   configured separately; use the generated `.mcp.json` as a connection reference.
5. Fully quit and restart WoW. Enable **WoW AI** and its **WoW AI slot** addons
   at character selection. New slot/signal files require a full game restart.
6. Double-click **Start-Goblin-Eye-Chat.cmd**, leave its console open and type
   `/wow-ai` in game. Use windowed or borderless mode for the pixel transport.
   Keep the dashboard running to import new saved observations.

For a custom client location or unattended setup, run in the extracted folder:

```powershell
.\Setup-WoWAI.cmd --wow "D:\Games\World of Warcraft\_classic_beta_" --account "YOUR_ACCOUNT" --agent kilo --yes
```

Setup copies only WoWAI, generates its reply slots, and writes **local** paths.
It backs up replaced local configuration/addon files under `wow-ai/backups`.
It does not install the CurseForge data addons or modify global client accounts.
Your realm, faction, region and ruleset remain the dashboard's market settings.

## Chat controls

Use **Chat settings** to select an agent and request its current model catalog.
Catalogs are discovered from supported installed CLIs and cached for five minutes;
refresh to request a new list. Unsupported/unavailable discovery does not invent
models: use the manual model ID field or the agent's default. Model, variant,
effort and permission choices apply per chat; changing them starts a new agent
session while preserving the displayed transcript. Price/free labels come from
the catalog and are not a billing guarantee.

Full replies can scroll/page. Research cards expand supported tool arguments,
results and item/evidence details. Resource URLs are copyable; the addon does not
launch arbitrary URLs or execute tool output. Large tool results have bounded
previews, with full records retained in private local research archives.

**Voice settings** provides Windows Desktop speech: Play TL;DR, Play full, Stop,
Test voice, volume, speed and optional automatic reading. Speech is off by default.
See [Voice controls](../wow-ai/VOICE.md). No Warcraft voice recordings or character
cloning assets are shipped.

## Permissions and privacy

Generated MCP connections expose the **read-only `mcp`** endpoint, not companion
write tools. Codex defaults to its read-only sandbox. Kilo's process-local
research policy denies shell, writes and delegation and allows enumerated Goblin
Eye research tools. The other CLI adapters enforce their own permission modes;
these are not equivalent sandboxes. Keep conservative defaults for game research.
Changing permissions or adding other MCP servers expands the agent's access.

The addon supplies character context and messages to the bridge. The pixel
transport reads a small on-screen message strip; reload mode uses SavedVariables.
Attached screenshots are optional and may be sent to your chosen AI provider,
as can prompts and tool results. Windows speech is local. The bridge does not
read game memory, inject code, send game inputs or automate gameplay/auctions.
This describes its behavior, not an endorsement or a guarantee against account
action. The player performs game actions.

Chats, research archives, screenshots, settings, credentials and saved player
data are private. Do not post them in bug reports or include them in shared ZIPs.

## Updates and troubleshooting

- **Agent missing / no reply:** check the bridge banner, run/log into that CLI
  manually in `Goblin-Eye-Chat`, and reconnect. A chat can select another agent.
- **MCP missing:** run setup, then start the CLI in the chat folder and approve
  project trust. Existing global servers belong to you; review conflicting
  duplicate `goblin_eye`/`goblin-eye` definitions in your client.
- **No current models:** refresh the model catalog or enter a known model ID.
- **Another bridge owns the files:** stop the earlier chat bridge; run one only.
- **Moved installation:** stop the bridge and rerun setup from the new folder
  with the same WoW client/account. It repairs local paths and preserves settings.
- **Upgrading:** extract the new ZIP separately. With both servers stopped, copy
  your own `data`, core `config.json`, and `wow-ai/bridge` local config/state/
  transcripts/speech-settings files. Rerun setup to repair paths and install the
  new addon, then restart WoW. Do not overwrite new bridge source with old source.
- **Grayed playback buttons:** wait for current playback or use Stop, then refresh
  voice status. Older replies need to remain in the local transcript.
- **Audio error:** test an installed Windows voice and check your output device.

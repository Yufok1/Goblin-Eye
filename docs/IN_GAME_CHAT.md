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
5. Fully quit and restart WoW. Open the game menu and its **AddOns** list.
   Enable **WoW AI** and its **WoW AI slot** addons. New slot/signal files require
   a full game restart.
6. Double-click **Start-Goblin-Eye-Chat.cmd**, leave its console open and type
   `/wow-ai` in game. Use windowed or borderless mode for the pixel transport.
   Keep the dashboard running to import new saved observations.

For a custom client location or unattended setup, run in the extracted folder:

```powershell
.\Setup-WoWAI.cmd --wow "D:\Games\World of Warcraft\_forever_" --account "YOUR_ACCOUNT" --agent kilo --yes
```

Setup copies only WoWAI, generates its reply slots, and writes **local** paths.
It backs up replaced local configuration/addon files under `wow-ai/backups`.
It does not install the CurseForge data addons or modify global client accounts.
Your realm, faction, region and ruleset remain the dashboard's market settings.

## Chat controls

Type `/wow-ai` or `/wowai` to open chat. `/wowai mini` shows the draggable
eye; click it to reopen the window. A new live installation may start hidden.

**Stop**, directly below Send, cancels the selected chat's running or queued AI
request and preserves your draft. Other chats keep running. `/wow-ai stop` and
`/wow-ai cancel` do the same thing. The next message starts a fresh agent session;
displayed history stays available. Stop cannot undo a tool action already completed.
In reload mode, click Reload to receive confirmation before sending the next draft.

Normal bridge startup never executes an old saved prompt. Accepted requests are
recorded before an agent launches; interrupted requests return a stopped notice
after a restart. Send a new message yourself to continue. Starting the bridge or
logging in does not resume that instruction. Explicit developer `--once`/`--inject`
commands remain available for deliberate test requests.

The bridge supplies saved conversation context automatically with every message,
including an already resumed agent session. It looks up the stable chat ID in
`wow-ai/bridge/transcripts.json`; there is no transcript search for the agent to
perform and no user-written handoff note is required. Existing transcripts work
without migration. Other chats are never used as a fallback for missing history.

Each completed reply can update an internal, validated task checkpoint containing
the current request, constraints, reported completed work and next step. The
checkpoint is stripped before display and speech, then saved atomically with the
chat transcript. If the client omits or malforms it, the bridge still supplies
verbatim conversation excerpts. This checkpoint is separate from Goblin Eye's
optional goals/notes database; missing goals do not erase saved chat context.

The handoff includes recent messages and is bounded to 32 KB; Antigravity uses
a smaller handoff within its command-line limit. The visible transcript retains
200 messages, while the checkpoint preserves the opening request and latest
task summary across that rolling limit. Excerpts and omitted messages are
labelled. These are historical conversation records, not current game facts.
Relevant character, quest and price evidence must still be refreshed.

Reloads and bridge restarts keep the chat identity. Model, agent, folder and Stop
changes can start a new provider session while retaining this chat's context.
An explicit missing-session error before any session/tool/progress activity gets
one automatic fresh-session attempt with the same handoff; active work and other
errors are never replayed automatically. Stop still prevents startup from
resuming an interrupted request. Deleting a chat deletes its checkpoint too.

Use **Chat settings** to select an agent, model and reasoning level. The bridge
keeps addon-saved model catalogs available locally. On Windows, automatic CLI
model probes are disabled by default to avoid unattended console/terminal
launches while playing. To opt in, set `backgroundModelDiscovery: true` in
`wow-ai/bridge/config.json` before starting chat. With that option enabled, the
bridge discovers catalogs at startup and every five minutes; failed discovery
retries after 30 seconds. Kilo has a 60-second discovery timeout. The
open menu checks for recovered lists for up to two minutes. The addon saves
complete catalogs; searching, paging, filtering and selecting models happen
locally without pixel-strip requests. **Check updates** reads the bridge's latest
published catalog; it does not launch discovery. With automatic probes disabled,
it continues to use the saved list or the agent's configured default rather than
fetching a new catalog. In reload transport mode, a manual
reload receives updates. The displayed timestamp identifies cached data, and a
failed refresh keeps the last usable list. Unsupported/unavailable discovery does
not invent models: use the agent's configured default. Model, variant,
effort and permission choices apply per chat; changing them starts a new agent
session while preserving the displayed transcript. Selections automatically travel
with the next chat message; there is no agent prompt to configure them. Voice
controls still use the existing bridge transport. Price/free labels come from
the catalog and are not a billing guarantee.

Full replies can scroll/page. Research cards expand supported tool arguments,
results and item/evidence details. Resource URLs are copyable; the addon does not
launch arbitrary URLs or execute tool output. Large tool results have bounded
previews, with full records retained in private local research archives.

**Prompts** opens a separate, draggable research library beside the chat. Search
the 28 bundled prompts, browse their summaries, and select one to read its full
contents in the scrolling preview. **Add to chat draft** appends it to your
current draft; every prompt is ready to send unchanged, using conversation and saved context. Browsing
uses no bridge requests or model calls. The library is generated from
`docs/prompt-power-pack` when the addon is built.

Every chat message carries the sender's addon-reported name and realm. The AI
uses that identity to select the matching saved character, including after an
alt switch. This is conversation metadata; levels, gear, stats and quests still
come from timestamped saved addon evidence. A missing or ambiguous match remains
explicitly unknown instead of selecting the newest imported alt.

Voice and model discovery run in a separate Goblin Eye companion worker. WoWAI
forwards controls and displays its status; the worker owns speech playback,
voice warming and model refreshes. Existing settings and in-game controls remain
the same. The launcher manages this worker automatically. If it restarts, saved
voice settings are restored without replaying old audio.

On Windows, agent CLIs run with a hidden console on a private background desktop.
Their native helpers inherit that desktop even when requesting a new console.
Goblin Eye never switches the player's desktop. If desktop creation fails, the
launch reports an error instead of falling back to a visible window.
The bundled Python runtime hosts this process; no extra installation is needed.

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

## Local storage

Goblin Eye keeps its database, bridge transcripts and research archives inside
the extracted folder. Its launchers and child tools use `data/runtime` for their
private home, AppData, temp files, package caches and speech/model caches. The
folder must be on a local non-system drive; C: and paths linked back to C: are
rejected. `GOBLIN_EYE_STORAGE_ROOT` can select another non-system-drive folder.
This setting affects only Goblin Eye processes, never your Windows environment.
Installed executables, Windows libraries and other read-only dependencies can
still be loaded from C:. Your separate Codex desktop app manages its own storage.

On the first start, the bridge copies only supported sign-in and settings files
into its private home. It leaves shared profiles and caches intact, does not copy
their histories/plugins/databases, and never overwrites an existing private
profile. Existing chats keep their saved task context and use fresh provider
session handles when their storage home changes. No pending action is resumed
merely because a home changed.

To sign in again or configure a CLI **for Goblin Eye**, run this from the package
folder, replacing `codex login` with the appropriate agent and CLI arguments:

```powershell
node wow-ai/bridge/agent-profile.js codex login
```

This uses the same private home as the chat bridge. Running an ordinary CLI
separately continues to use that CLI's independent profile. An expired or
unsupported provider sign-in may still require its normal authentication flow.

Chats, research archives, screenshots, settings, credentials and saved player
data are private. Do not post them in bug reports or include them in shared ZIPs.

## Updates and troubleshooting

- **Agent missing / no reply:** check the bridge banner, run/log into that CLI
  manually in `Goblin-Eye-Chat`, and reconnect. A chat can select another agent.
- **MCP missing:** run setup, then start the CLI in the chat folder and approve
  project trust. Existing global servers belong to you; review conflicting
  duplicate `goblin_eye`/`goblin-eye` definitions in your client.
- **AGY acknowledges but cannot research:** Antigravity print mode denies tool
  calls that still require approval. Configure scoped `mcp(goblin-eye/TOOL_NAME)`
  allow rules for the read-only tools you authorize in Antigravity's permission
  settings, then send the request again. WoWAI reports these soft denials as an
  incomplete request even if AGY labels its acknowledgement `SUCCESS`.
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

Neural speech uses explicit UTF-8 pipe streams, including Windows installations
with a legacy system code page. Private voice assets and runtime paths may live
outside this folder; see [private voice portability](../wow-ai/LOCAL-VOICES.md).

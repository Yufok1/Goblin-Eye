# Game access boundary

Audited October 7, 2026 against the active Goblin Eye checkout, installed Alts
extension, optional WoWAI bridge and staged research changes.

## Research backend

Goblin Eye's Python/MCP backend reads addon SavedVariables, installed static
addon catalogs and its SQLite database. Public reference feeds use ordinary
HTTP; these are not connections to the game client or gameplay servers. Its
local HTTP socket serves the dashboard. The CLI's localhost connection probes
whether that dashboard is already running.

Inspection found no game process handles, memory reads/writes, input synthesis,
game-window screenshots, injected code, game commands, auction actions or
combat/movement monitoring in the research backend. Lua imports use the
bounded literal parser, not evaluation of saved addon code. Regression tests
scan the backend for process/capture/input dependencies and unsafe OS API
symbols. They also check the observation extension for gameplay-action calls.

The setup helper writes Goblin Eye's owned Lua observation file and reviewed
Alts manifests with backups. This is an addon filesystem installation, not a
runtime process attachment. A changed addon contract is rejected before file
mutation.

## In-game observations

Only the Alts Forever extension calls game APIs for research capture. It reads
encountered full item links, item stats/tooltips/metadata, character-sheet
values, selected trait nodes, helpful buffs and completed quest IDs using
normal addon APIs. It does not send gameplay inputs or perform auctions.

Character-sheet reads happen outside lockdown on ordinary addon events with
a debounce. Deferred work resumes after lockdown. No current health/power
sampling, combat log, kill rate, movement log, target surveillance or gameplay
automation is added. Item loading uses the standard addon item-data request
and bounded retries. No item, character, realm, faction or quest ID is patched
into runtime logic to fill a report gap.

## Authorized chat-only exception

The user explicitly retained WoWAI's existing addon chat-strip transport.
Its external capture helper locates the window and reads the region containing
the addon-generated pixel strip. On Windows this uses ClientToScreen, IsIconic
and Graphics.CopyFromScreen. The decoder requires the strip header and checksum.
It supplies conversation messages, not character/item research observations.
Replies are written as normal addon files and read by the addon.

No game-memory access or gameplay-input calls were found in the inspected
capture implementations. The Linux capture helper additionally sets a window
compositor property; it is not the configured Windows capture path. macOS
window discovery uses System Events to read window bounds.

Speech's OpenProcess use requests SYNCHRONIZE access to its own bridge/launcher
parents so orphaned audio workers exit. speech.js passes its own process ID;
this is not a game-process memory handle. Bridge cancellation terminates its
owned agent children, not the game. WoWAI chat edit-box hooks route manually
submitted agent messages and leave ordinary chat behavior to its original UI
handlers. No equipment-stat provider was found in the WoWAI addon.

## Scope

These findings cover inspected first-party source and known OS-facing paths.
They do not certify every external agent CLI, third-party plugin, installed
addon or packaged dependency. Agent research instructions prohibit direct game
access; an independently configured CLI can have capabilities outside the MCP
server. Static regression checks are architecture guards, not a proof about
arbitrary external programs or every future code change.

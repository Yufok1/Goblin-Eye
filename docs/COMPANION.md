# Goblin Eye companion

Goblin Eye carries player goals, notes, and session reports between agent conversations. It does not run an AI model. Any client that supports local stdio MCP can use the same research and companion tools without requiring a particular model provider.

## What it stores

- **Goals** are things the player wants to work toward. Mark them active, completed, or archived.
- **Notes** hold context worth retaining.
- **Session reports** record what the player says happened during play. `created_at` is the note time; optional `occurred_at` is a separately supplied, timezone-qualified event time.

Each entry has a basis: `player_report`, `agent_inference`, or `sourced_evidence`. Sourced evidence requires at least one explicit reference. `author` records who saved it, either player through the dashboard/CLI or agent through MCP. These fields label claims; they do not independently verify them. Titles and bodies are immutable. Archive an incorrect entry and add a corrected one; status changes are retained in `companion_status_events`.

An optional `character_snapshot_id` associates an entry with one imported export. The export can be stale and is not live character state. `get_companion_context` returns a bounded handoff with active goals, recent notes, latest character snapshot pointers, and the user-confirmed auction workspace. Agents should then query current Goblin Eye evidence for the actual question.

## Use it

1. Run `Start-Goblin-Eye.cmd` once to initialize the database. Back up existing data before upgrading; migrations add empty tables without seeding personal entries.
2. Open the local dashboard and select **Companion** to add or review entries.
3. Follow [Agent setup](AGENT_SETUP.md) to connect your client to this folder's `Start-Agent.cmd`. No personal MCP configuration is bundled.
4. Ask the agent to read `get_companion_context`, research your current question, and save only the specific context you want retained.

The ordinary `goblin-eye mcp` command remains read-only. `companion-mcp` adds `add_companion_entry` and `set_companion_status` to the read-only research and companion tools. The writable commands only change companion records; they cannot perform WoW actions, change auction data, or alter character exports. Existing MCP processes must reconnect to discover new tools.

CLI fallback:

```powershell
.\python\python.exe -m goblin_eye companion
.\python\python.exe -m goblin_eye companion-add goal "Prepare for a dungeon" "Research gear and quests before going"
.\python\python.exe -m goblin_eye companion-status 1 completed
```

Read-only HTTP endpoints are `/api/companion/context`, `/api/companion/entries`, and `/api/companion/entries/{id}`. Dashboard writes use local JSON POST endpoints. They accept loopback clients only and reject cross-origin browser requests. The dashboard is not an account-authenticated remote service.

`reset-personal-data` deletes companion entries and their status history along with character exports and auction evidence. `reset-auctions` retains companion entries. The database is local and gitignored.

## Agent discipline

Read the handoff at the start of a relevant conversation, then ask which goal matters when several could apply. Use `get_economic_summary` and its `auction_context` before economic conclusions. Use `list_characters` and the intended `get_character_snapshot` before personal gear or adventure conclusions. Treat notes and session reports as user statements or agent interpretations, not live telemetry. Never turn an agent inference into a player report. Do not log gameplay automatically or perform in-game actions.

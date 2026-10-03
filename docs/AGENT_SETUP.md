# Connect your agent client

Goblin Eye has no embedded AI model. Its local stdio MCP interface gives an
MCP-compatible client access to research and optional goals/notes. Start the
dashboard once to initialize the database before connecting an agent.

Configure your client's local stdio server with these fields, substituting the
absolute path where you extracted the ZIP:

```json
{
  "command": "cmd.exe",
  "args": ["/d", "/c", "C:\\YOUR_FOLDER\\Goblin-Eye\\Start-Agent.cmd"]
}
```

The path may contain spaces; keep it as a single args entry. The launcher sets
the working directory and Python import path itself. Paste these fields into
the local MCP-server configuration format your client expects. Project-specific
configuration from the developer's computer is deliberately not included.

Start-Agent.cmd launches `companion-mcp`: research tools plus bounded writes to
your companion goals and notes. It cannot perform WoW actions or alter auction
and character evidence. For strictly read-only MCP, use:

```json
{
  "command": "powershell.exe",
  "args": [
    "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
    "C:\\YOUR_FOLDER\\Goblin-Eye\\Run-Goblin-Eye.ps1", "-ReadOnlyMcp"
  ]
}
```

Do not run Start-Agent.cmd expecting a chat window: it waits for the client to
send MCP protocol messages. Reconnect the client after replacing application
source files. The dashboard can stay running alongside MCP to import saves.

Suggested first request:

> Read my Goblin Eye companion context and source health. Use sourced evidence
> to investigate my question, distinguish observations from inference, identify
> missing data, and show capture timestamps and provenance. Save notes only
> when I ask or when they are clearly part of an agreed goal.

For character advice, query `list_characters` then the selected
`get_character_snapshot`. For prices, start with `get_economic_summary` and
its auction_context, then use explicit source and market keys. Local faction,
ruleset, region and realm are unknown until explicitly configured or reported by
a supported source; do not infer them, and do not treat the software default as
confirmation of a player's server. Public regional prices are separate from
local addon observations.

Fallback from PowerShell in this folder:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.\.venv\Scripts\python.exe -m goblin_eye characters
.\.venv\Scripts\python.exe -m goblin_eye sources
.\.venv\Scripts\python.exe -m goblin_eye companion
```

Local HTTP: `http://127.0.0.1:8765/api/characters`, `/api/sources`,
`/api/companion/context`, and `/api/health` (adjust port if configured).

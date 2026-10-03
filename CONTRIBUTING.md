# Contributing to Goblin Eye

Goblin Eye is a local evidence browser and MCP server for WoW Forever. Start
with [Architecture](docs/ARCHITECTURE.md) and [Data connections](docs/DATA_CONNECTIONS.md).
Windows is the supported end-user platform. CI also exercises portable Python
code on Linux. Each database holds one local market profile; faction, ruleset,
region and realm default to unknown and must not be asserted on a user's
behalf. Tests use synthetic market profiles.

## Development setup

Use Python 3.10+ and Node.js 22+ for development. Runtime Python code uses the
standard library. From the repository root on PowerShell:

```powershell
py -3 -m venv .venv
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
npm ci --ignore-scripts
npm run build
```

On Linux/macOS, the equivalent test command is
`PYTHONPATH=src python3 -m unittest discover -s tests -v`. The Windows launchers
are the supported installation route. A development editable install is optional;
a pip wheel alone is not a supported end-user distribution because migrations
and dashboard assets live alongside the source checkout.

Commit regenerated `web/dist` assets when changing `web/src`. CI rebuilds the
dashboard and checks that the committed output matches. Use synthetic fixtures
in tests; keep test discovery isolated from the developer's installed addons.

## Changes and evidence

- Preserve capture time, import time, source, market, build and confidence.
- Keep static catalog assertions separate from live observations and completed sales.
- Do not execute addon Lua, control gameplay, inspect game memory, or invent missing fields.
- Never commit personal databases, SavedVariables, logs, account paths, credentials,
  model configurations, or downloaded third-party addon packages.
- Document inspected source versions and unknowns when adding an importer.
- Keep migrations additive and preserve existing evidence. Destructive maintenance
  commands are not an installation or troubleshooting step.
- Keep runtime dependencies minimal and update CHANGELOG.md for user-visible changes.

Run the relevant tests, the dashboard build when changed, and the release verifier
for packaging changes. Open a PR explaining the problem, resulting behavior and
validation. Use the issue template for bugs, with personal information removed.

## Make a release

See [Release process](docs/RELEASING.md). The build uses an explicit file list;
it must never zip the working directory wholesale.

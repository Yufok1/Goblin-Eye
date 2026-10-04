# Contributing to Goblin Eye

Goblin Eye is a local evidence browser and MCP server for WoW Forever. Start
with [Architecture](docs/ARCHITECTURE.md) and [Data connections](docs/DATA_CONNECTIONS.md).
Windows is the supported end-user platform. CI also exercises portable Python
code on Linux. Each database holds one local market profile; faction, ruleset,
region and realm default to unknown and must not be asserted on a user's
behalf. Tests use synthetic market profiles.

## Development setup

Use the vendored interpreter in `python/` and Node.js 22+ for development. Runtime
Python code uses the standard library. From the repository root on PowerShell:

```powershell
.\python\python.exe -m unittest discover -s tests -v
npm ci --ignore-scripts
npm run build
py -3 scripts\fetch_python.py --check
```

On Linux/macOS, use `python3 -m unittest discover -s tests -v` with
`PYTHONPATH=src`; the bundled runtime is Windows-only. The Windows launchers are
the supported installation route. A development editable install is optional; a
pip wheel alone is not a supported end-user distribution because migrations and
dashboard assets live alongside the source checkout.

Commit regenerated `web/dist` assets when changing `web/src`, and commit the
vendored `python/` runtime. CI rebuilds the dashboard and checks that the
committed output matches. Use synthetic fixtures in tests; keep test discovery
isolated from the developer's installed addons.

## Vendored Python runtime

`python/` holds the official CPython Windows embeddable distribution, pinned by
version, URL and SHA-256 in `scripts/python_runtime.json`. It is committed so a
GitHub source download runs without the player installing Python, on the same
principle as the committed `web/dist`.

- `python scripts/fetch_python.py --check` verifies the installed runtime
  offline. Run it in CI-style checks before packaging.
- `python scripts/fetch_python.py` re-downloads the pinned upstream build.
- To move to a new Python release, update the pin first, then re-run the fetch
  script, then commit the resulting `python/` directory and the changed pin.
- Do not hand-edit files under `python/`, and do not relax the hash check. The
  build refuses to package an interpreter that does not match the pin.
- `Run-Goblin-Eye.ps1` prefers `python/python.exe` and falls back to an
  accessible system Python only when that directory is absent.

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

# Requirements

## Run the shared application

- Windows with Windows PowerShell 5.1 or newer.
- Python 3.10 or newer, accessible as `py`, `python`, or `python3`.
- An extracted folder you can write to, for the local environment and database.
- A browser for the dashboard (default http://127.0.0.1:8765/).

Need Python? Follow [INSTALL-PYTHON.md](INSTALL-PYTHON.md) before starting.

Python runtime dependencies: **none outside the standard library**.
`requirements.txt` intentionally has comments only. It is a valid pip
requirements file; `python -m pip install -r requirements.txt` installs nothing.
The Windows launchers do not need pip or download Python packages.
Node.js, npm, a database server, and administrator privileges are not needed.

## Optional: connect an AI client

- Your separately installed AI client, with any account setup it requires.
- Support for launching a **local stdio MCP server**.
- The Start-Agent.cmd command configured in that client's MCP settings, as
  described in docs/AGENT_SETUP.md. Use its absolute path on each friend's PC.
- Run Start-Goblin-Eye.cmd once before connecting, and keep the dashboard running
  when you want saved addon observations imported automatically.

Goblin Eye does not supply a model, model API credentials, agent subscription,
or chat interface. The chosen agent handles conversations, credentials and
any billing. Goblin Eye supplies evidence and optional companion notes through
MCP. No model-provider key is required in Goblin Eye's config.json.

An AI subscription is not required to run the dashboard. Direct optional AI
access requires a client that supports local MCP; otherwise you can copy
sourced dashboard results into your chosen chat service. WoWAI is not required.

Each friend gets their own local database and settings. Do not copy somebody
else's data/ directory or config.json as part of setup. Each database records one
local market profile; faction, ruleset, region and realm stay unknown until the
player sets them or a supported source reports them. Set them in `config.json`
when you know them. All six public AHledger Forever markets remain separate
reference sources.

## Optional data and networking

WoW Forever and compatible, user-installed addons are needed for personal game
observations. None is required to open the empty dashboard. Supported sources
include Alts Forever, Auctionator, AHledger, ProfessionDB, Forever Guide,
QuestieDB, and Mapzeroth. Follow the complete addon list and download links in
[START-HERE.md](START-HERE.md). Addons are not bundled or
automatically installed. Goblin Eye reads saved files after /reload or logout.

Internet access is needed for AHledger public syncing, official Blizzard page
caching, and any networked AI client you choose. Local saved-file research and
the dashboard can run offline.
The dashboard binds to loopback by default; friends run their own copies.

## Development only

- Node.js/npm to install the pinned TypeScript compiler and rebuild web assets:
  `npm ci` then `npm run build`.
- For an optional editable Python install: `python -m pip install -e .`.
  Its build backend requires setuptools >=68, as declared in pyproject.toml.
- Full source-checkout tests: `python -m unittest discover -s tests -v`.
  The share ZIP does not include test fixtures or developer tooling directories.

These development steps are not part of your friends' normal setup.

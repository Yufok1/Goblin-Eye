# Supported agent adapters

Install and authenticate the CLI you want to use separately. The bridge finds
installed CLIs or uses `agents.<id>.path` in local `bridge/config.json`. It never
bundles accounts, keys or subscriptions. Run the CLI once in `Goblin-Eye-Chat`
and approve project trust/MCP before headless chat.

| Adapter ID | Client | Setup reference | Permission behavior |
| --- | --- | --- | --- |
| `codex` | OpenAI Codex CLI | `npm install -g @openai/codex`, then `codex` | `default` selects read-only sandbox; `acceptEdits` workspace-write; bypass removes the sandbox. |
| `claude` | Claude Code | [Claude Code](https://code.claude.com/docs/en/setup), then `claude` | CLI permission mode plus allow/deny rules. Read-only Goblin Eye MCP tools are allowed by the supplied config; this is not an OS sandbox. |
| `kilo` | Kilo CLI | [Kilo CLI](https://kilo.ai/docs/code-with-ai/platforms/cli), then `kilo` | Process-local `goblin-research` policy denies shell, writes and delegation; permits enumerated research tools. `researchOnly` stays true by default. |
| `grok` | Grok CLI | Install the CLI supported by `agents.js`, log in with `grok login` | CLI approval/deny flags; no equivalent Codex sandbox. Configure MCP in your client. |
| `agy` | Antigravity CLI | Install Google Antigravity CLI and run `agy` | `default` uses plan mode; other modes follow CLI flags. Configure MCP in your client. |
| `hermes` | Hermes Agent | Install Hermes Agent and run `hermes setup` | Uses the client's own approval policy; the bridge never passes `--yolo`. Configure MCP in your client. |

Adapters track different CLI event formats and can break when a client changes.
Codex, Claude and Kilo receive generated **local read-only** MCP connections
from `Setup-WoWAI.cmd`; Grok, Antigravity and Hermes need client-specific MCP
setup. Their parsers/session behavior have fixture tests, not a promise that
every current provider/model is available on every PC.

`bridge/config.json` controls the default agent. The settings window changes
the agent/model/variant/effort/permission for a chat without editing that file.
An agent or settings change starts a new CLI session with its existing displayed
history intact. Each agent resumes its own session where supported. Kilo receives
prompts on stdin to avoid the Windows argument-length limit. Antigravity has a
bounded command-line prompt. Hermes tool research cards have limited coverage.

Dynamic model discovery uses the installed CLI's supported catalog/cache;
Kilo supports live model enumeration. Some clients expose only cached choices
or no discovery. Refresh/manual model ID/default are available. The bridge does
not promise that a listed model is free or that your account can access it.

`allowedTools`/`deniedTools` apply to Claude/Grok CLI rules; Codex ignores those
lists and uses its sandbox. Kilo has no CLI allowlist switches: its separate
process-local policy enforces the research companion restrictions. Changing
`permissionMode` alone cannot disable `researchOnly:true`. Never assume another
adapter provides that same boundary. User-configured MCP servers retain their
own privileges; this project only generates a read-only Goblin Eye endpoint.

Credentials remain in the client-managed profile. Setup does not mutate global
client configuration. Project settings and transcripts are private, ignored
files. See [in-game setup and privacy](../../docs/IN_GAME_CHAT.md).

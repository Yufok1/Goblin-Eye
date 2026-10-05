# WoWAI — Goblin Eye edition

Optional in-game chat for Goblin Eye. This is a modified MIT-licensed copy of
[chelinho139/wow-ai](https://github.com/chelinho139/wow-ai), with the original
copyright and [license](LICENSE) retained.

Start with [the complete installation guide](../docs/IN_GAME_CHAT.md). Run
`Setup-WoWAI.cmd` at the Goblin Eye package root, then
`Start-Goblin-Eye-Chat.cmd`. Windows requires Node.js 22.2+ and a separately
installed, configured agent CLI. No npm runtime dependencies or bundled model.

This edition adds expandable Goblin Eye tool/evidence cards, readable full
replies and source links, per-chat settings, supported dynamic model catalogs,
Kilo headless sessions, a single-bridge lock, bounded publishing/rendering and
optional [Windows Desktop speech](VOICE.md). Character-cloning recordings and
neural voice runtimes are excluded.

The game sends messages/context via an on-screen pixel strip or saved variables;
the bridge writes reply-slot addon files, and the game loads them. It does not
send game inputs, read game memory or automate gameplay. Screenshots attached by
the player and research data may be sent to the chosen agent/provider.

## Development

From a Git source checkout (tests are excluded from the runtime ZIP), run
`npm ci --ignore-scripts`, then `npm test` in this directory. The suite
uses mock game APIs, fake agents and scratch client folders; it requires no
account or live game. Windows also verifies noisy pixel-strip round trips.
`build-addon.js` generates the reload-compatible `addon/WoWAI/WoWAI.lua` from
its source modules; commit the generated file when changing those modules.

The optional `npm run test:live` is a separate opt-in developer check using a
configured real agent in a scratch directory. Do not run `--inject` against a
live bridge's state files. Local configs, histories, captures and backups are
ignored and excluded from distribution.

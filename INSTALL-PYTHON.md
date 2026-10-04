# Python is already included

**You do not need to install Python.** The Goblin Eye ZIP ships its own Python
runtime in a `python` folder next to the application.

Nothing to download, nothing to install, no administrator access, no changes to
your system. Extract the ZIP and run `Start-Goblin-Eye.cmd`.

## What is in the folder

```
Goblin-Eye/
  python/        <- bundled Python 3.12 runtime; do not move or rename it
  src/           <- Goblin Eye source
  migrations/    <- database migrations
  web/           <- prebuilt dashboard
  Start-Goblin-Eye.cmd
```

The launcher uses `python\python.exe` automatically. Keep the `python` folder
inside the Goblin Eye folder; moving `src` or `python` on its own will break the
launcher.

## Requirements

- Windows 10 or Windows 11
- A writable folder to extract into
- A browser

That is the complete list. Node.js, npm, pip, an AI subscription, and an API key
are all optional or unnecessary.

## If you want to update Python yourself

You do not need to. The bundled runtime is pinned and hash-verified. If you are
checking or refreshing it as a developer, run:

```powershell
py -3 scripts\fetch_python.py --check
py -3 scripts\fetch_python.py
```

The first command verifies the installed runtime against the pinned archive hash
without network access. The second re-downloads the pinned upstream build.

## If you prefer to use your own Python

The launcher falls back to any accessible Python 3.10 or newer if the bundled
`python` folder is absent. This is intended for development checkouts. Some
players find it useful to keep a system Python for scripting.

## Why a bundled runtime

Windows does not ship Python, and asking every player to install an interpreter
before they can look at a dashboard is the single largest setup barrier. A
portable runtime keeps Goblin Eye a one-double-click install with no system
modification, and it works offline.

The bundled build is the official Python embeddable distribution. It is
redistributed under the Python Software Foundation license; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

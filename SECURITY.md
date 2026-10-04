# Security and private data

Goblin Eye is designed for a local computer. Keep its HTTP listener on loopback;
it is not an authenticated internet-facing service. The read-only MCP endpoint
exposes local evidence, and the optional companion endpoint can write goals and
notes. Connect only clients you intend to give access to that information.

The Windows ZIP bundles a Python runtime. It is the unmodified official CPython
embeddable distribution, pinned by SHA-256 in `scripts/python_runtime.json`.
Verify a downloaded copy with `python scripts/fetch_python.py --check` if you
want to confirm the hash matches the pin.

Do not put account identifiers, SavedVariables, databases, tokens, full logs or
unredacted screenshots in public issues or pull requests. Bug reports should use
minimal synthetic examples and sanitized error messages.

For a vulnerability, use the repository's **Security → Report a vulnerability**
when private reporting is enabled. If unavailable, ask the maintainer for a
private reporting channel without posting exploit details or private data.

The current development release is the maintained version. Fixes are delivered
through updated source and Windows release ZIPs.

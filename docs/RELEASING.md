# Release process

Versions in `src/goblin_eye/__init__.py`, `pyproject.toml`, `package.json` and
`package-lock.json` must agree. Update CHANGELOG.md, run tests, rebuild the
dashboard, and commit the intended release first.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
py -3 -m unittest discover -s tests -v
npm ci --ignore-scripts
npm run build
py -3 scripts/build_release.py
py -3 scripts/verify_release.py dist/Goblin-Eye-0.1.0-Windows.zip
```

The builder first checks that the version in `src/goblin_eye/__init__.py`,
`pyproject.toml`, `package.json` and `package-lock.json` agree, verifies the
vendored `python/` runtime against the pin in `scripts/python_runtime.json`,
reads the version from the project, and writes a ZIP, SHA-256 sidecar, and
per-file manifest under `dist`. Replace the sample version in the verifier
command when releasing a different version. Identical input files produce an
identical ZIP. The builder uses an explicit allowlist, never zips the working
directory wholesale, never imports personal evidence, never writes into the
source checkout, and refuses to package `config.json`, a generated directory, or
a user-scoped local path.

The verifier extracts the archive into a folder whose path contains spaces,
checks the manifest hashes, starts the archive's **own** bundled interpreter to
prove it works without a system Python, migrates a fresh database, drives both
MCP entry points over stdio, and confirms the prebuilt dashboard. On Windows it
also runs `Run-Goblin-Eye.ps1 -InitializeOnly` and `Start-Agent.cmd`, and fails
if the launcher tries to create a `.venv`. On other platforms those launcher
checks are reported as skipped and the portable checks still run, using the host
interpreter because the bundled runtime is Windows-only. It fails if a fresh
install asserts any faction, ruleset or region. The report is written next to
the archive as `Goblin-Eye-<version>-Windows.validation.json`.

The release workflow runs on a pushed `v*` tag, verifies that the tag matches the
project version, confirms the committed dashboard is current, runs the tests,
builds and verifies the ZIP, then creates a **draft** GitHub release with the
archive, its SHA-256 sidecar, and the validation report. The tag must point at
the release commit. Review the draft and its assets before publishing it. CI and
PR builds only upload workflow artifacts. Only the release job holds `contents:
write`.

For example, after the release commit is pushed and CI has passed:

```text
git tag v0.1.0
git push origin v0.1.0
```

Enable private vulnerability reporting in repository settings. Keep GitHub
Actions read-only by default; only the release job needs contents write access.
Use branch protection for main once the first CI checks have run.

The repository includes the prebuilt dashboard so GitHub source downloads can
also run with the included Windows launcher. Friends should normally choose the
versioned Windows ZIP from Releases. The ZIP contains START-HERE.md and all setup
documents, but no personal config, database, saved addon data, AI credentials,
development environment, or third-party game addons.

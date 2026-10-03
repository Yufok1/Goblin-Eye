# Install Python on Windows

Goblin Eye requires Python 3.10 or newer. Its requirements.txt does not install
Python. These instructions are for Windows 10/11.

## Check first

Open Start, type **PowerShell**, and open it. Run:

```powershell
py -3 --version
```

If you see Python 3.10 or a newer 3.x version, skip installation and continue
with START-HERE.md. If `py` is unavailable, also try `python --version`.

## Install from Python.org

1. Open the official [Python Windows downloads page](https://www.python.org/downloads/windows/).
2. Download the **Python install manager**. Open the downloaded file and select
   **Install**. Follow any configuration prompts.
3. Open a new PowerShell window and install the default stable Python runtime:

   ```powershell
   pymanager install default
   ```

4. Confirm the runtime is available:

   ```powershell
   py -3 --version
   ```

The install manager installs and manages Python runtimes; downloading the
manager alone is not the same as installing the runtime. The explicit install
command above handles that step. Python's official documentation describes
the [Windows installation process](https://docs.python.org/3/using/windows.html).

## Start Goblin Eye

Extract the entire Goblin Eye ZIP, then double-click **Start-Goblin-Eye.cmd**.
It creates a local Python environment and initializes the database. No pip
packages are required. AI setup is optional; get the dashboard working first.

## If commands are not recognized

Close and reopen PowerShell after installation. If commands still fail, use
the [official Windows troubleshooting guide](https://docs.python.org/3/using/windows.html#troubleshooting).
An older `py` launcher may conflict with the new manager; `pymanager` is the
manager-specific command. Do not uninstall an existing working Python just
to use Goblin Eye: any accessible Python 3.10+ is sufficient.

Python itself is not bundled in the Goblin Eye ZIP. Initial downloads require
internet access; Goblin Eye's launcher uses the Python already installed.

param(
    [switch]$Mcp,
    [switch]$ReadOnlyMcp,
    [switch]$InitializeOnly,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
Set-Location -LiteralPath $packageRoot
$env:PYTHONPATH = Join-Path $packageRoot 'src'
$env:PYTHONUNBUFFERED = '1'
$pythonPath = Join-Path $packageRoot '.venv\Scripts\python.exe'

function Find-Python {
    # Check candidates rather than accepting the Windows Store execution alias.
    foreach ($candidate in @('py', 'python', 'python3')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        $prefix = @()
        if ($candidate -eq 'py') { $prefix = @('-3') }
        try {
            $probe = & $command.Source @prefix -c 'import sys; print(sys.executable) if sys.version_info >= (3, 10) else sys.exit(1)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $probe -and (Test-Path -LiteralPath ([string]$probe))) {
                return [string]$probe
            }
        } catch { continue }
    }
    throw 'Python 3.10 or newer is required. Install Python for Windows, then run this launcher again.'
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    $installedPython = Find-Python
    # The application uses the Python standard library: no pip downloads needed.
    & $installedPython -m venv --without-pip (Join-Path $packageRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
}
& $pythonPath -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'The local environment requires Python 3.10 or newer.' }

if ($Mcp -or $ReadOnlyMcp) {
    # Stdio belongs to MCP. Do not emit setup messages or initialize a DB here.
    $mode = 'companion-mcp'
    if ($ReadOnlyMcp) { $mode = 'mcp' }
    & $pythonPath -m goblin_eye $mode
    exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath 'config.json')) {
    Copy-Item -LiteralPath 'config.example.json' -Destination 'config.json'
}
& $pythonPath -m goblin_eye init
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed. See the error above.' }
if ($InitializeOnly) { exit 0 }

$settings = Get-Content -LiteralPath 'config.json' -Raw | ConvertFrom-Json
$dashboardUrl = 'http://{0}:{1}/' -f $settings.host, $settings.port
Write-Host "Dashboard: $dashboardUrl"
Write-Host 'Leave this window open while using Goblin Eye. Press Ctrl+C to stop.'
if (-not $NoBrowser) { Start-Process $dashboardUrl }
& $pythonPath -m goblin_eye serve
exit $LASTEXITCODE

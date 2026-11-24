# Process-local only; never changes Windows/user environment settings.
$taskStorageRoot = $env:GOBLIN_EYE_STORAGE_ROOT
if (-not $taskStorageRoot) { $taskStorageRoot = Join-Path $PSScriptRoot 'data\runtime' }
$taskStorageRoot = [IO.Path]::GetFullPath($taskStorageRoot)
$taskStorageDrive = [IO.Path]::GetPathRoot($taskStorageRoot).TrimEnd('\')
if ($taskStorageDrive -eq 'C:' -or $taskStorageDrive -eq $env:SystemDrive -or $taskStorageRoot.StartsWith('\\')) {
    throw 'Goblin Eye runtime storage must be on D: or another local non-system drive.'
}
$taskStorageSpec = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime-storage.json') -Raw | ConvertFrom-Json
foreach ($taskKey in @('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','GROK_HOME','CODEX_HOME','CLAUDE_CONFIG_DIR','XDG_CONFIG_HOME','XDG_DATA_HOME')) {
    $taskExisting = [Environment]::GetEnvironmentVariable($taskKey, 'Process')
    if ($taskExisting -and -not [Environment]::GetEnvironmentVariable("GOBLIN_EYE_HOST_$taskKey", 'Process')) {
        [Environment]::SetEnvironmentVariable("GOBLIN_EYE_HOST_$taskKey", $taskExisting, 'Process')
    }
}
foreach ($taskEntry in $taskStorageSpec.directories.PSObject.Properties) {
    $taskDirectory = Join-Path $taskStorageRoot $taskEntry.Value
    # Inspect every existing ancestor before New-Item can follow a junction.
    $taskAncestor = $taskDirectory
    while ($taskAncestor) {
        if (Test-Path -LiteralPath $taskAncestor) {
            $taskItem = Get-Item -LiteralPath $taskAncestor -Force
            if ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Storage directory is a link: $taskAncestor" }
        }
        $taskParent = [IO.Directory]::GetParent($taskAncestor)
        $taskAncestor = if ($taskParent) { $taskParent.FullName } else { $null }
    }
    $null = New-Item -ItemType Directory -Path $taskDirectory -Force
    [Environment]::SetEnvironmentVariable($taskEntry.Name, $taskDirectory, 'Process')
}
foreach ($taskEntry in $taskStorageSpec.values.PSObject.Properties) {
    [Environment]::SetEnvironmentVariable($taskEntry.Name, [string]$taskEntry.Value, 'Process')
}
$env:GOBLIN_EYE_STORAGE_ROOT = $taskStorageRoot
$env:HOMEDRIVE = $taskStorageDrive
$env:HOMEPATH = $env:USERPROFILE.Substring(2)

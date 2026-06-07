#Requires -Version 5.1
# sessionStart: mark activity and start the 5-minute auto-push watcher if not already running.
$ErrorActionPreference = "SilentlyContinue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$HooksDir = Join-Path $RepoRoot ".cursor\hooks"
$LocalDir = Join-Path $RepoRoot ".local"
$PidFile = Join-Path $LocalDir "auto-push-watcher.pid"
$ActivityFile = Join-Path $LocalDir "cursor-activity.timestamp"
$WatcherScript = Join-Path $HooksDir "auto-push-watcher.ps1"

if (-not (Test-Path -LiteralPath $LocalDir)) {
    New-Item -ItemType Directory -Path $LocalDir -Force | Out-Null
}

[DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString() | Set-Content -LiteralPath $ActivityFile -Encoding ASCII -NoNewline

if (Test-Path -LiteralPath $PidFile) {
    $existingPid = (Get-Content -LiteralPath $PidFile -Raw -ErrorAction SilentlyContinue).Trim()
    if ($existingPid -and (Get-Process -Id ([int]$existingPid) -ErrorAction SilentlyContinue)) {
        exit 0
    }
}

Start-Process -FilePath "powershell.exe" `
    -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden",
        "-File", $WatcherScript
    ) `
    -WorkingDirectory $RepoRoot | Out-Null

exit 0

#Requires -Version 5.1
# Records Cursor activity for the auto-push watcher (stdin JSON from hook is ignored).
$ErrorActionPreference = "SilentlyContinue"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LocalDir = Join-Path $RepoRoot ".local"
$StampFile = Join-Path $LocalDir "cursor-activity.timestamp"

if (-not (Test-Path -LiteralPath $LocalDir)) {
    New-Item -ItemType Directory -Path $LocalDir -Force | Out-Null
}

[DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString() | Set-Content -LiteralPath $StampFile -Encoding ASCII -NoNewline
exit 0

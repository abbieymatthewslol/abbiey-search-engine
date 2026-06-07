#Requires -Version 5.1
<#
  Background loop: while Cursor activity is recent, commit and push at most every 15 minutes.
  Started once per workspace session via sessionStart hook.
#>
$ErrorActionPreference = "SilentlyContinue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$LocalDir = Join-Path $RepoRoot ".local"
$ActivityFile = Join-Path $LocalDir "cursor-activity.timestamp"
$LastPushFile = Join-Path $LocalDir "auto-push-last.timestamp"
$PidFile = Join-Path $LocalDir "auto-push-watcher.pid"
$LogFile = Join-Path $LocalDir "auto-push-watcher.log"

$ActivityWindowSec = 900   # consider "active" if activity within last 15 minutes
$PushIntervalSec = 900     # push at most every 15 minutes while active
$PollSec = 60

if (-not (Test-Path -LiteralPath $LocalDir)) {
    New-Item -ItemType Directory -Path $LocalDir -Force | Out-Null
}

$MyPid = $PID
Set-Content -LiteralPath $PidFile -Value $MyPid -Encoding ASCII

function Write-Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Get-UnixTime([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    $raw = (Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue).Trim()
    if (-not $raw) { return 0 }
    return [int64]$raw
}

function Test-HasTrackableChanges {
    $porcelain = git status --porcelain 2>$null
    if (-not $porcelain) { return $false }
    foreach ($line in $porcelain) {
        if ($line.Length -lt 4) { continue }
        $path = $line.Substring(3).Trim('"')
        if ($path -match '^\.env(\.|$)|credentials|\.local/|vercel_token') { continue }
        return $true
    }
    return $false
}

function Test-SafeToStage {
    $names = git diff --name-only 2>$null
    $staged = git diff --cached --name-only 2>$null
    $all = @()
    if ($names) { $all += $names }
    if ($staged) { $all += $staged }
    foreach ($name in $all) {
        if ($name -match '^\.env(\.|$)|credentials|secret|\.local/|vercel_token') {
            return $false
        }
    }
    return $true
}

Write-Log "watcher started pid=$MyPid"

try {
    while ($true) {
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        $lastActivity = Get-UnixTime $ActivityFile
        $lastPush = Get-UnixTime $LastPushFile
        $activityAge = $now - $lastActivity
        $pushAge = $now - $lastPush

        if ($lastActivity -gt 0 -and $activityAge -le $ActivityWindowSec -and $pushAge -ge $PushIntervalSec) {
            if ((Test-HasTrackableChanges) -and (Test-SafeToStage)) {
                git add -A 2>$null | Out-Null
                if (-not (Test-SafeToStage)) {
                    git reset -q 2>$null
                    Write-Log "skip: sensitive paths detected after staging"
                }
                else {
                    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                    $msg = "chore(auto): sync cursor activity $stamp"
                    git commit -m $msg 2>$null | Out-Null
                    if ($LASTEXITCODE -eq 0) {
                        $pushScript = Join-Path $RepoRoot "scripts\push-and-notify.ps1"
                        if (Test-Path -LiteralPath $pushScript) {
                            & powershell -NoProfile -ExecutionPolicy Bypass -File $pushScript -SkipVercelWait 2>&1 | Out-Null
                        }
                        else {
                            git push origin HEAD 2>$null | Out-Null
                        }
                        if ($LASTEXITCODE -eq 0) {
                            $now.ToString() | Set-Content -LiteralPath $LastPushFile -Encoding ASCII -NoNewline
                            Write-Log "pushed: $msg"
                        }
                        else {
                            Write-Log "push failed (exit $LASTEXITCODE)"
                        }
                    }
                }
            }
        }

        Start-Sleep -Seconds $PollSec
    }
}
finally {
    if (Test-Path -LiteralPath $PidFile) {
        $onDisk = (Get-Content -LiteralPath $PidFile -Raw -ErrorAction SilentlyContinue).Trim()
        if ($onDisk -eq "$MyPid") {
            Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Log "watcher stopped pid=$MyPid"
}

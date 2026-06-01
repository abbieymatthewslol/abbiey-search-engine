#Requires -Version 5.1
<#
.SYNOPSIS
  Watch the repo and automatically commit + push settled source changes to the live branch.

.DESCRIPTION
  This helper polls `git status --porcelain` on a short interval, waits for a quiet
  debounce window, then creates an auto-generated commit and runs `push-and-notify.ps1`.
  Pushes to `main` trigger the existing GitHub Actions -> Vercel production deploy path.

  The watcher refuses to start against a dirty worktree by default so it does not
  accidentally publish unrelated local changes. Use -AllowDirtyStart only if you want
  the current state treated as the baseline.
#>
[CmdletBinding()]
param(
    [int] $PollSeconds = 3,
    [int] $QuietSeconds = 12,
    [string] $Remote = "origin",
    [string] $Branch = "",
    [switch] $AllowDirtyStart,
    [switch] $PushEnv,
    [switch] $SkipVercelWait
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Get-CurrentBranch {
    $b = (git branch --show-current 2>$null).Trim()
    if (-not $b) {
        throw "Detached HEAD or empty branch; checkout a branch before starting auto-live-sync."
    }
    return $b
}

function Get-StatusLines {
    $lines = @(git status --porcelain=v1 --untracked-files=all 2>$null)
    if ($LASTEXITCODE -ne 0) {
        throw "git status failed."
    }
    return @($lines | Where-Object {
        $_ -and
        $_ -notmatch '^\?\? \.github/copilot-instructions\.md$' -and
        $_ -notmatch '^\?\? abbiey search\.txt$'
    })
}

function Join-Status([string[]] $lines) {
    if (-not $lines -or $lines.Count -eq 0) { return "" }
    return [string]::Join("`n", $lines)
}

function Get-StageablePaths([string[]] $baselineLines, [string[]] $currentLines) {
    $baselineSet = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($line in $baselineLines) {
        [void]$baselineSet.Add($line)
    }

    $paths = New-Object 'System.Collections.Generic.List[string]'
    foreach ($line in $currentLines) {
        if ($baselineSet.Contains($line)) {
            continue
        }
        if ($line.Length -lt 4) {
            continue
        }
        $entry = $line.Substring(3)
        if (-not $entry) {
            continue
        }
        if ($entry -match ' -> ') {
            $parts = $entry -split ' -> ', 2
            foreach ($part in $parts) {
                if ($part) {
                    $paths.Add($part)
                }
            }
            continue
        }
        $paths.Add($entry)
    }

    return @($paths | Select-Object -Unique)
}

function Invoke-GitCommit([string] $message, [string] $body) {
    git commit -m $message -m $body
    return $LASTEXITCODE
}

if (-not $Branch) {
    $Branch = Get-CurrentBranch
}

$initialStatus = Get-StatusLines
if ($initialStatus.Count -gt 0 -and -not $AllowDirtyStart) {
    throw ("Working tree is not clean. Commit/stash current changes first, or re-run with -AllowDirtyStart.`n" +
           ($initialStatus -join "`n"))
}

$lastSnapshot = Join-Status $initialStatus
$baselineLines = @($initialStatus)
$lastChangeAt = Get-Date

Write-Host ("Watching {0} on branch {1}. Poll={2}s Quiet={3}s" -f $RepoRoot, $Branch, $PollSeconds, $QuietSeconds) -ForegroundColor Cyan
Write-Host "Auto-live-sync is active. Press Ctrl+C to stop." -ForegroundColor DarkGray

while ($true) {
    Start-Sleep -Seconds $PollSeconds
    $currentLines = Get-StatusLines
    $currentSnapshot = Join-Status $currentLines

    if ($currentSnapshot -ne $lastSnapshot) {
        $lastSnapshot = $currentSnapshot
        $lastChangeAt = Get-Date
        if ($currentLines.Count -gt 0) {
            Write-Host ("Change detected at {0}" -f (Get-Date -Format "HH:mm:ss")) -ForegroundColor Yellow
        }
        continue
    }

    if (-not $currentSnapshot) {
        continue
    }

    $quietFor = ((Get-Date) - $lastChangeAt).TotalSeconds
    if ($quietFor -lt $QuietSeconds) {
        continue
    }

    Write-Host ("Changes settled after {0:N0}s. Creating auto-live commit..." -f $quietFor) -ForegroundColor Cyan
    $stageablePaths = Get-StageablePaths $baselineLines $currentLines
    if (-not $stageablePaths -or $stageablePaths.Count -eq 0) {
        $lastSnapshot = $currentSnapshot
        $lastChangeAt = Get-Date
        continue
    }

    git add -A -- @stageablePaths
    if ($LASTEXITCODE -ne 0) {
        throw "git add failed."
    }

    $staged = @(git diff --cached --name-only 2>$null)
    if (-not $staged -or $staged.Count -eq 0) {
        $lastSnapshot = ""
        continue
    }

    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $commitMsg = 'chore(live): auto-sync ' + $stamp
    $commitBody = "Auto-synced settled local edits for live deployment.`n`nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
    $commitExit = Invoke-GitCommit $commitMsg $commitBody
    if ($commitExit -ne 0) {
        Write-Warning "git commit did not succeed; waiting for the next change."
        $lastChangeAt = Get-Date
        continue
    }

    $pushScript = Join-Path $PSScriptRoot "push-and-notify.ps1"
    if ($SkipVercelWait) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $pushScript -Remote $Remote -Branch $Branch -SkipVercelWait
    }
    else {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $pushScript -Remote $Remote -Branch $Branch
    }
    if ($LASTEXITCODE -ne 0) {
        throw "push-and-notify.ps1 failed."
    }

    if ($PushEnv -and (Test-Path (Join-Path $RepoRoot ".env"))) {
        python (Join-Path $RepoRoot "scripts\restore_vercel_env.py") --apply
        if ($LASTEXITCODE -ne 0) {
            throw "restore_vercel_env.py --apply failed."
        }
    }

    $baselineLines = @(Get-StatusLines)
    $lastSnapshot = Join-Status $baselineLines
    $lastChangeAt = Get-Date
}

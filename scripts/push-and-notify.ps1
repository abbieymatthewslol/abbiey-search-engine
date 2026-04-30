#Requires -Version 5.1
<#
.SYNOPSIS
  Push current branch to origin, optionally wait for Vercel production deploy, show Windows tray notifications.

.PARAMETER Remote
  Git remote (default: origin).

.PARAMETER Branch
  Branch to push (default: current).

.PARAMETER SkipVercelWait
  Git push only; one notification.

.PARAMETER MaxWaitMinutes
  Max minutes to poll Vercel API for READY (default: 15).

.NOTES
  Set ABBIEY_PRODUCTION_BRANCH to override the production branch this helper
  waits on (defaults to main).

  VERCEL_TOKEN: use user env, or run scripts/store-vercel-token.ps1 once to save
  an encrypted token under .local/vercel_token.secure (Windows DPAPI).
#>
[CmdletBinding()]
param(
    [string] $Remote = "origin",
    [string] $Branch = "",
    [switch] $SkipVercelWait,
    [int] $MaxWaitMinutes = 15
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Read-StoredVercelToken {
    $path = Join-Path $RepoRoot ".local\vercel_token.secure"
    if (-not (Test-Path -LiteralPath $path)) {
        return $null
    }
    try {
        $enc = ([System.IO.File]::ReadAllText($path)).Trim()
        if (-not $enc) { return $null }
        $sec = ConvertTo-SecureString -String $enc
        $cred = New-Object System.Management.Automation.PSCredential ("vercel", $sec)
        return $cred.GetNetworkCredential().Password
    }
    catch {
        Write-Warning "Could not decrypt .local/vercel_token.secure (wrong Windows user or machine?): $($_.Exception.Message)"
        return $null
    }
}

# Match .vercel/project.json (Vercel CLI) — single source of truth for API polling
$projectId = "prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b"
$teamId = "team_YeguIG4NHm4Kp0Jf5AbOwgFN"
$vercelProjectPath = Join-Path $RepoRoot ".vercel\project.json"
if (Test-Path -LiteralPath $vercelProjectPath) {
    try {
        $vc = Get-Content -LiteralPath $vercelProjectPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($vc.projectId) { $projectId = [string]$vc.projectId }
        # Vercel stores team id as orgId in project.json; REST API uses teamId=
        if ($vc.orgId) { $teamId = [string]$vc.orgId }
    }
    catch {
        Write-Warning "Could not parse .vercel/project.json: $($_.Exception.Message)"
    }
}

function Show-DeployNotification {
    param(
        [string] $Title,
        [string] $Body,
        [ValidateSet("Info", "Error")]
        [string] $Kind = "Info"
    )
    $fm = $ExecutionContext.SessionState.LanguageMode
    if ($fm -eq "ConstrainedLanguage" -or $fm -eq "NoLanguage") {
        $color = if ($Kind -eq "Error") { "Red" } else { "Green" }
        Write-Host ""
        Write-Host ("=== {0} ===" -f $Title) -ForegroundColor $color
        Write-Host $Body -ForegroundColor $color
        Write-Host "===================" -ForegroundColor $color
        Write-Host ""
        return
    }
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
        $ni = New-Object System.Windows.Forms.NotifyIcon
        $ni.Visible = $true
        if ($Kind -eq "Error") {
            $ni.Icon = [System.Drawing.SystemIcons]::Error
            $tip = [System.Windows.Forms.ToolTipIcon]::Error
        }
        else {
            $ni.Icon = [System.Drawing.SystemIcons]::Information
            $tip = [System.Windows.Forms.ToolTipIcon]::Info
        }
        $ni.ShowBalloonTip(22000, $Title, $Body, $tip)
        Start-Sleep -Milliseconds 500
        $ni.Dispose()
    }
    catch {
        Write-Warning "Tray notification unavailable: $($_.Exception.Message)"
        Write-Host ("{0}: {1}" -f $Title, $Body)
    }
}

if (-not $Branch) {
    $Branch = (git branch --show-current).Trim()
}
if (-not $Branch) {
    throw "Detached HEAD or empty branch; checkout a branch first."
}

$productionBranch = $env:ABBIEY_PRODUCTION_BRANCH
if (-not $productionBranch) {
    $productionBranch = "main"
}

$commitSha = (git rev-parse HEAD).Trim()

Write-Host "Pushing $Branch to $Remote (commit $commitSha) ..." -ForegroundColor Cyan
cmd.exe /c ('cd /d "{0}" && git push -u {1} {2}' -f $RepoRoot, $Remote, $Branch)
if ($LASTEXITCODE -ne 0) {
    Show-DeployNotification -Title "abbiey.search - GitHub" -Body "Push failed for $Branch." -Kind Error
    throw "git push failed with exit code $LASTEXITCODE"
}

if ($SkipVercelWait) {
    Show-DeployNotification -Title "abbiey.search - GitHub" -Body "Pushed $Branch to $Remote." -Kind Info
    Write-Host "Done." -ForegroundColor Green
    exit 0
}

if ($Branch -ne $productionBranch) {
    $msg = "Pushed $Branch to $Remote. Production deploy tracking only runs for $productionBranch."
    Show-DeployNotification -Title "abbiey.search - GitHub" -Body $msg -Kind Info
    Write-Host $msg -ForegroundColor DarkYellow
    exit 0
}

Show-DeployNotification -Title "abbiey.search - GitHub" -Body "Pushed $Branch. Waiting for Vercel production..." -Kind Info

$tok = $env:VERCEL_TOKEN
if (-not $tok) {
    $tok = Read-StoredVercelToken
}
if (-not $tok) {
    Show-DeployNotification -Title "abbiey.search - Vercel" -Body "Set user env VERCEL_TOKEN or run scripts/store-vercel-token.ps1 for encrypted local token." -Kind Info
    Write-Warning "VERCEL_TOKEN not set and no .local/vercel_token.secure; skipping Vercel API poll."
    exit 0
}

$headers = @{ Authorization = "Bearer $tok" }
$deadline = (Get-Date).AddMinutes($MaxWaitMinutes)
# Vercel REST: filter by full git SHA (reliable; walking meta.githubCommitSha in list items was unreliable in PowerShell)
$encSha = [System.Uri]::EscapeDataString($commitSha)
# Production on abbieysearch.com follows the configured production branch (main by default).
$uri = "https://api.vercel.com/v6/deployments?projectId=$projectId&teamId=$teamId&sha=$encSha&limit=5"
$shortSha = if ($commitSha.Length -ge 7) { $commitSha.Substring(0, 7) } else { $commitSha }
Write-Host "Polling Vercel (project=$projectId, sha=$shortSha...)" -ForegroundColor DarkGray

$poll = 0
do {
    Start-Sleep -Seconds 10
    $poll += 1
    try {
        $resp = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -TimeoutSec 40
    }
    catch {
        Show-DeployNotification -Title "abbiey.search - Vercel API" -Body $_.Exception.Message -Kind Error
        throw
    }

    $list = @($resp.deployments)
    if ($list.Count -lt 1) {
        if ($poll -eq 1) {
            Write-Host "No production deployment for this SHA yet. GitHub Actions may still be building; a short delay before the SHA appears in Vercel is normal." -ForegroundColor DarkYellow
        }
        if ($poll % 3 -eq 0) {
            Write-Host ("Still waiting for Vercel to register commit {0}... {1}" -f $shortSha, (Get-Date -Format "HH:mm:ss"))
        }
        continue
    }

    $dep = $null
    foreach ($d in $list) {
        if ($d.target -eq 'production') {
            $dep = $d
            break
        }
    }
    if (-not $dep) { $dep = $list[0] }
    $state = [string]$dep.readyState
    if ($state -eq "READY") {
        $deployUrl = "https://abbieysearch.com"
        if ($dep.url) {
            $deployUrl = "https://" + ($dep.url -replace '^https?://', '')
        }
        Show-DeployNotification -Title "abbiey.search - Vercel" -Body ("Production deploy READY.`n{0}" -f $deployUrl) -Kind Info
        Write-Host "Vercel READY: $deployUrl" -ForegroundColor Green
        exit 0
    }
    if ($state -eq "ERROR" -or $state -eq "CANCELED") {
        Show-DeployNotification -Title "abbiey.search - Vercel" -Body "Deploy state: $state" -Kind Error
        throw "Vercel deployment readyState=$state"
    }

    Write-Host ("Build state: {0}  {1}" -f $state, (Get-Date -Format "HH:mm:ss"))
} while ((Get-Date) -lt $deadline)

Show-DeployNotification -Title "abbiey.search - Vercel" -Body "Timed out waiting for READY. Check Vercel dashboard." -Kind Info
Write-Warning "No READY within $MaxWaitMinutes minutes."
exit 0

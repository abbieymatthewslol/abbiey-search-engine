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

function Show-DeployNotification {
    param(
        [string] $Title,
        [string] $Body,
        [ValidateSet("Info", "Error")]
        [string] $Kind = "Info"
    )
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop | Out-Null
    Add-Type -AssemblyName System.Drawing -ErrorAction Stop | Out-Null
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

$teamId = "team_YeguIG4NHm4Kp0Jf5AbOwgFN"
$projectId = "prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b"

if (-not $Branch) {
    $Branch = (git branch --show-current).Trim()
}
if (-not $Branch) {
    throw "Detached HEAD or empty branch; checkout a branch first."
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

Show-DeployNotification -Title "abbiey.search - GitHub" -Body "Pushed $Branch. Waiting for Vercel production..." -Kind Info

$tok = $env:VERCEL_TOKEN
if (-not $tok) {
    Show-DeployNotification -Title "abbiey.search - Vercel" -Body "Set user env VERCEL_TOKEN to auto-detect deploy READY after push." -Kind Info
    Write-Warning "VERCEL_TOKEN not set; skipping Vercel API poll."
    exit 0
}

$headers = @{ Authorization = "Bearer $tok" }
$deadline = (Get-Date).AddMinutes($MaxWaitMinutes)
$uri = "https://api.vercel.com/v6/deployments?projectId=$projectId&teamId=$teamId&limit=25"

do {
    Start-Sleep -Seconds 10
    try {
        $resp = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -TimeoutSec 40
    }
    catch {
        Show-DeployNotification -Title "abbiey.search - Vercel API" -Body $_.Exception.Message -Kind Error
        throw
    }

    $list = @($resp.deployments)
    $dep = $null
    foreach ($d in $list) {
        $ds = $null
        if ($d.meta -and ($d.meta | Get-Member -Name githubCommitSha -ErrorAction SilentlyContinue)) {
            $ds = [string]$d.meta.githubCommitSha
        }
        if ($ds -eq $commitSha) {
            $dep = $d
            break
        }
    }

    if (-not $dep) {
        Write-Host ("No deployment row for commit {0} yet... {1}" -f $commitSha, (Get-Date -Format "HH:mm:ss"))
        continue
    }

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

#Requires -Version 5.1
<#
.SYNOPSIS
  One-shot: verify git, optional env sync (existing scripts), production deploy, live probes.

.DESCRIPTION
  Does NOT duplicate env logic - uses scripts/verify_production_env.py and scripts/restore_vercel_env.py.
  Invokes Vercel via scripts/vercel-cli.cmd (npx.cmd) so Constrained Language Mode does not break npx.ps1.

.PARAMETER PushEnv
  Run restore_vercel_env.py --apply (requires repo-root .env with secrets).

.PARAMETER SkipPull
  Skip git pull --ff-only.

.PARAMETER SkipDeploy
  Validate and pull only; no production deploy.

.PARAMETER SiteUrl
  Public site for health checks (default https://abbieysearch.com).

.PARAMETER StrictProbes
  Fail the script if live GET /health or GET / fails after retries (default: warn only on 429/WAF).
#>
[CmdletBinding()]
param(
    [switch] $PushEnv,
    [switch] $SkipPull,
    [switch] $SkipDeploy,
    [switch] $StrictProbes,
    [string] $SiteUrl = "https://abbieysearch.com"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Write-Cmd($line) {
    Write-Host "`n>>> $line" -ForegroundColor Cyan
}

function Invoke-RepoCmd([string] $Inner) {
    cmd.exe /c ('cd /d "{0}" && {1}' -f $RepoRoot, $Inner)
}

Write-Cmd "git remote -v"
Invoke-RepoCmd "git remote -v"

Write-Cmd "git branch --show-current"
Invoke-RepoCmd "git branch --show-current"

$origin = (& git -C $RepoRoot config --get remote.origin.url 2>$null)
if ($origin) { $origin = $origin.Trim() }
if ($origin -and $origin -notmatch "abbieymatthewslol/abbiey-search-engine(-2)?(\.git)?$") {
    Write-Warning ("origin is not the canonical repo (see .cursor/rules git-canonical-origin). Current: {0}" -f $origin)
}

function Invoke-WebWith429Retry {
    param(
        [scriptblock] $Action,
        [int] $Attempts = 5,
        [int] $SleepSeconds = 8
    )
    for ($i = 1; $i -le $Attempts; $i++) {
        try {
            return & $Action
        }
        catch {
            $code = $null
            if ($_.Exception.Response) { try { $code = [int]$_.Exception.Response.StatusCode } catch {} }
            if ($code -ne 429 -and $_.Exception.Message -notmatch "429") {
                throw
            }
            if ($i -eq $Attempts) { throw }
            Write-Warning ("HTTP 429 from probe, retry {0}/{1} after {2}s" -f $i, $Attempts, $SleepSeconds)
            Start-Sleep -Seconds $SleepSeconds
        }
    }
}

if (-not $SkipPull) {
    Write-Cmd "git pull --ff-only origin (current branch)"
    $branch = (git branch --show-current).Trim()
    Invoke-RepoCmd ("git pull --ff-only origin {0}" -f $branch)
}

Write-Cmd "Vercel whoami (uses VERCEL_TOKEN from your user env)"
Invoke-RepoCmd "scripts\vercel-cli.cmd whoami"
if ($LASTEXITCODE -ne 0) { throw "Vercel CLI auth failed. Set VERCEL_TOKEN or run scripts\vercel-cli.cmd login" }

Write-Cmd "vercel pull production (refresh .vercel project linkage + local env files)"
Invoke-RepoCmd "scripts\vercel-cli.cmd pull --yes --environment=production"

if (Test-Path (Join-Path $RepoRoot ".env")) {
    Write-Cmd "python scripts/verify_production_env.py --strict"
    python (Join-Path $RepoRoot "scripts\verify_production_env.py") --strict
    if ($LASTEXITCODE -ne 0) { throw "verify_production_env.py --strict failed; fix .env before deploy." }

    if ($PushEnv) {
        Write-Cmd "python scripts/restore_vercel_env.py --apply"
        python (Join-Path $RepoRoot "scripts\restore_vercel_env.py") --apply
        if ($LASTEXITCODE -ne 0) { throw "restore_vercel_env.py --apply failed." }
    }
    else {
        Write-Host ''
        Write-Host 'Skipping restore_vercel_env.py --apply; re-run with -PushEnv to upsert Vercel env from .env' -ForegroundColor Yellow
    }
}
else {
    Write-Warning 'No .env at repo root - skipped verify_production_env --strict and env push. Create .env for full checks.'
}

if (-not $SkipDeploy) {
    Write-Cmd "vercel deploy --prod --yes"
    Invoke-RepoCmd "scripts\vercel-cli.cmd deploy --prod --yes"
    if ($LASTEXITCODE -ne 0) { throw "vercel deploy failed." }
}

$base = $SiteUrl.TrimEnd("/")
Write-Cmd ("Invoke-RestMethod GET {0}/health (public JSON health; not /api/health)" -f $base)
$healthUri = ("{0}/health" -f $base)
try {
    $h = Invoke-WebWith429Retry -Action { Invoke-RestMethod -Uri $healthUri -Method Get -TimeoutSec 45 }
    $h | ConvertTo-Json -Compress -Depth 5
}
catch {
    $msg = "Live GET /health failed after retries: {0}" -f $_
    if ($StrictProbes) { throw $msg }
    Write-Warning $msg
}

Write-Cmd ("GET {0}/ root HTML smoke" -f $base)
try {
    $r = Invoke-WebWith429Retry -Action { Invoke-WebRequest -Uri $base -Method Get -TimeoutSec 45 -UseBasicParsing }
    Write-Host "status=$($r.StatusCode) len=$($r.RawContentLength)"
}
catch {
    $msg = "Live GET / failed after retries: {0}" -f $_
    if ($StrictProbes) { throw $msg }
    Write-Warning $msg
}

# Optional admin probe when secrets exist in this shell / .env-loaded child
$pingScript = Join-Path $RepoRoot "scripts\verify_production_env.py"
if ((Test-Path (Join-Path $RepoRoot ".env"))) {
    Write-Cmd 'python scripts/verify_production_env.py --ping'
    python $pingScript --ping
}

Write-Host ''
Write-Host ('Done. Live URL: ' + $SiteUrl) -ForegroundColor Green

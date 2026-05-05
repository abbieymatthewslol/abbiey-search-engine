# Sets GitHub Actions secret NPM_TOKEN for the npm publish workflow (needs gh CLI).
# Prefers: NPM_TOKEN env, then -Path file (one line), then clipboard (must start with npm_).
# Usage:
#   powershell -NoProfile -File scripts/set-github-npm-secret-from-clipboard.ps1
#   powershell -NoProfile -File scripts/set-github-npm-secret-from-clipboard.ps1 -Path .local/npm_token.txt
param(
    [string] $Path = ""
)
$ErrorActionPreference = "Stop"
$repo = "abbieymatthewslol/abbiey-search-engine-2"
$tok = $null
$proc = [Environment]::GetEnvironmentVariable("NPM_TOKEN", "Process")
$user = [Environment]::GetEnvironmentVariable("NPM_TOKEN", "User")
$machine = [Environment]::GetEnvironmentVariable("NPM_TOKEN", "Machine")
if ($proc) { $tok = $proc.Trim() }
elseif ($user) { $tok = $user.Trim() }
elseif ($machine) { $tok = $machine.Trim() }
elseif ($Path -ne "" -and (Test-Path -LiteralPath $Path)) {
    $tok = (Get-Content -LiteralPath $Path -Raw).Trim()
}
if (-not $tok) {
    $c = Get-Clipboard -Raw -ErrorAction SilentlyContinue
    if (-not [string]::IsNullOrWhiteSpace($c)) { $tok = $c.Trim() }
}
if ([string]::IsNullOrWhiteSpace($tok)) {
    Write-Error "No token: set NPM_TOKEN env, or copy npm token (npm_) to clipboard, then run again."
    exit 1
}
if (-not $tok.StartsWith("npm_")) {
    Write-Error "Token must start with npm_ (npm granular/automation token). Refusing to set secret."
    exit 1
}
$tok | gh secret set NPM_TOKEN --repo $repo
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
Write-Host "GitHub secret NPM_TOKEN set for $repo"

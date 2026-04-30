#Requires -Version 5.1
<#
.SYNOPSIS
  Save VERCEL_TOKEN encrypted on disk (Windows DPAPI, current user only).

.DESCRIPTION
  Uses ConvertFrom-SecureString (DPAPI). The ciphertext is useless on other
  machines or for other Windows users. Never commit .local/

.PARAMETER SecureToken
  If omitted, prompted securely (recommended).

.PARAMETER Clear
  Remove the stored ciphertext file only.

.NOTES
  If your token was ever pasted into chat or logs, revoke it in Vercel and create a new one before storing.
#>
[CmdletBinding(DefaultParameterSetName = 'Save')]
param(
    [Parameter(ParameterSetName = 'Save')]
    [SecureString] $SecureToken,

    [Parameter(ParameterSetName = 'Clear')]
    [switch] $Clear
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dir = Join-Path $RepoRoot ".local"
$file = Join-Path $dir "vercel_token.secure"

if ($Clear) {
    if (Test-Path -LiteralPath $file) {
        Remove-Item -LiteralPath $file -Force
        Write-Host "Removed encrypted token file." -ForegroundColor Green
    }
    else {
        Write-Host "No stored token file at $file" -ForegroundColor DarkYellow
    }
    exit 0
}

if (-not $SecureToken) {
    Write-Host "Paste VERCEL_TOKEN (input hidden):" -ForegroundColor Cyan
    $SecureToken = Read-Host -AsSecureString
}
if (-not $SecureToken) {
    throw "Empty token; aborting."
}
$probe = (New-Object System.Management.Automation.PSCredential ("_", $SecureToken)).GetNetworkCredential().Password
if ([string]::IsNullOrWhiteSpace($probe)) {
    throw "Empty token; aborting."
}

New-Item -ItemType Directory -Force -Path $dir | Out-Null
$encrypted = ConvertFrom-SecureString $SecureToken
[System.IO.File]::WriteAllText($file, $encrypted.Trim(), [System.Text.UTF8Encoding]::new($false))
Write-Host "Stored encrypted token at:" -ForegroundColor Green
Write-Host "  $file"
Write-Host "This file is gitignored. Env VERCEL_TOKEN still overrides when set." -ForegroundColor DarkGray

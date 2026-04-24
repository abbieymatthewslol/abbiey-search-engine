@echo off
setlocal
rem Run Vercel CLI from repo root. Use this when PowerShell Constrained Language Mode breaks npx.ps1.
rem Usage: scripts\vercel-cli.cmd login
rem        scripts\vercel-cli.cmd whoami
rem        scripts\vercel-cli.cmd pull --yes --environment=production
rem
rem For "vercel login", clear a bad VERCEL_TOKEN in this window first:  set VERCEL_TOKEN=
rem (Do not put tokens in this file; use Windows User env or GitHub Actions secrets.)

cd /d "%~dp0.."

rem Only strip env tokens for browser login so an old VERCEL_TOKEN does not override.
if /i "%~1"=="login" (
  set "VERCEL_TOKEN="
  set "VERCEL_OIDC_TOKEN="
)

if exist "%ProgramFiles%\nodejs\npx.cmd" (
  "%ProgramFiles%\nodejs\npx.cmd" --yes vercel@latest %*
  exit /b %ERRORLEVEL%
)
if exist "%ProgramFiles(x86)%\nodejs\npx.cmd" (
  "%ProgramFiles(x86)%\nodejs\npx.cmd" --yes vercel@latest %*
  exit /b %ERRORLEVEL%
)

npx --yes vercel@latest %*
exit /b %ERRORLEVEL%

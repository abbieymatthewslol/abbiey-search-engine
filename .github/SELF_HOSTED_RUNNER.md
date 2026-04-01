# Self-hosted GitHub Actions runner (Windows)

Use this when you want workflows (for example Vercel deploy) to run on your own machine instead of GitHub-hosted `ubuntu-latest`.

**Security**

- Registration tokens are **single-use** and **secret**. Generate a new one from the repo each time: **Settings → Actions → Runners → New self-hosted runner** (or org-level runners).
- Never commit tokens, paste them into issues/chats, or store them in this repo. If a token was exposed, remove the runner registration in GitHub and create a new runner with a **new** token.

## Install (PowerShell, folder at drive root)

Adjust the drive letter if needed (`C:` below). Pick the **latest** runner version from [actions/runner releases](https://github.com/actions/runner/releases) and update the ZIP URL and filename.

```powershell
mkdir C:\actions-runner
cd C:\actions-runner

$version = "2.333.1"   # update to match the release you download
$zip = "actions-runner-win-x64-$version.zip"
Invoke-WebRequest -Uri "https://github.com/actions/runner/releases/download/v$version/$zip" -OutFile $zip

# Optional: validate SHA256 from the release notes / SHASUMS on the release page
# $expected = "PASTE_SHA256_FROM_RELEASE"
# if ((Get-FileHash -Path $zip -Algorithm SHA256).Hash.ToUpper() -ne $expected.ToUpper()) { throw "Checksum mismatch" }

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory("$PWD\$zip", "$PWD")
```

## Configure and run

From `C:\actions-runner` (after extract):

```powershell
.\config.cmd --url https://github.com/OWNER/REPO --token YOUR_REGISTRATION_TOKEN
.\run.cmd
```

For a service that survives logoff, use `.\svc.cmd` after configuration (see GitHub’s docs).

## Use in workflows

Set the job to use your runner:

```yaml
jobs:
  deploy:
    runs-on: self-hosted
```

Example: in `.github/workflows/deploy.yml`, change `runs-on: ubuntu-latest` to `runs-on: self-hosted` **only** on a branch or fork where this Windows runner is registered and online. The default in this repo stays `ubuntu-latest` so GitHub-hosted CI keeps working without a runner.

## Requirements

- Node.js and npm (for `vercel` CLI in the deploy workflow).
- Network access to GitHub and Vercel.
- Repository secret `VERCEL_TOKEN` still required for deploy steps.

## References

- [Adding self-hosted runners](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners)
- [actions/runner releases](https://github.com/actions/runner/releases)

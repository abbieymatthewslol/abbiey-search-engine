#!/usr/bin/env bash
# One command: OSINT modules + Flask dev server (from repo root).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export ABBIEY_OSINT_MODULES="${ABBIEY_OSINT_MODULES:-dns,rdap,ptr,tls,dig,whois}"
echo "[+] ABBIEY_OSINT_MODULES=$ABBIEY_OSINT_MODULES"
echo "[+] http://127.0.0.1:8000"
exec python3 app.py

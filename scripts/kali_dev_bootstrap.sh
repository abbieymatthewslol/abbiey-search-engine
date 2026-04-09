#!/usr/bin/env bash
# Install common CLI dependencies on Kali/Debian/Ubuntu hosts so OSINT dig/whois modules work.
set -euo pipefail
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y dnsutils whois ca-certificates python3-venv python3-pip
else
  echo "No apt-get; install dig (BIND) and whois for your OS, then set e.g."
  echo "  export ABBIEY_OSINT_MODULES=dns,rdap,ptr,tls,dig,whois"
  exit 1
fi
echo "Done. Add to .env:"
echo "  ABBIEY_OSINT_MODULES=dns,rdap,ptr,tls,dig,whois"

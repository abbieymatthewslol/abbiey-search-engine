#!/usr/bin/env python3
"""One-shot auth integration sync (Supabase Site URL + redirect allow list). Delegates to sync_supabase_auth_config.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    target = root / "sync_supabase_auth_config.py"
    raise SystemExit(subprocess.call([sys.executable, str(target)] + sys.argv[1:]))

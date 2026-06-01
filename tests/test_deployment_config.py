"""Deployment config regression tests for the Vercel production path."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_vercel_include_files import verify as verify_vercel_config  # noqa: E402


def test_vercel_json_skips_git_builds_on_main():
    cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    ignore_command = str(cfg.get("ignoreCommand") or "")
    assert "VERCEL_GIT_COMMIT_REF" in ignore_command
    assert "main" in ignore_command
    assert "exit 0" in ignore_command
    assert "exit 1" in ignore_command


def test_verify_vercel_config_passes_for_repo_state():
    errors, warnings = verify_vercel_config()
    assert errors == []
    assert isinstance(warnings, list)

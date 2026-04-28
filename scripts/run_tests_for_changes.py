"""
Run a minimal pytest set from git-changed files (CI and local dev).

* Critical paths (app entrypoint, test harness, deps) -> full ``pytest tests/``.
* Otherwise: direct module mapping + ``rg`` on ``tests/`` for route/module names.
* Falls back to a small smoke set if nothing matches.

Env (optional, from GitHub Actions):
  DIFF_BASE, DIFF_HEAD   SHAs for ``git diff --name-only`` (inclusive of changes in range).
  RUN_FULL_TESTS=1     Force the full ``pytest tests/`` (e.g. manual CI override).

Usage:
  python scripts/run_tests_for_changes.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

# Touching these always runs the full Python suite.
FULL_SUITE_FILES = frozenset(
    {
        "conftest.py",
        "requirements.txt",
        "pyproject.toml",
        "pytest.ini",
        "setup.py",
    }
)
FULL_SUITE_PATH_PREFIXES = (
    "tests/conftest",
    ".github/workflows",
)

# Prefix / filename fragment -> test files (repo-relative).
PATH_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("app.py", ("tests/test_app.py", "tests/test_feature_gates.py", "tests/test_health_features.py")),
    ("api_v1.py", ("tests/test_api_v1.py",)),
    ("api/", ("tests/test_app.py",)),  # serverless entry; smoke
    ("billing.py", ("tests/test_api_v1.py", "tests/test_app.py")),
    ("entity_parser.py", ("tests/test_entity_parser.py",)),
    ("people_finder.py", ("tests/test_people_finder.py",)),
    ("query_understanding.py", ("tests/test_query_understanding.py",)),
    ("retrieval/", ("tests/test_retrieval.py",)),
    ("osint/", ("tests/test_osint.py",)),
    ("search_bots.py", ("tests/test_search_bots_api.py",)),
    ("bot_crawler.py", ("tests/test_search_bots_api.py",)),
    ("reverse_image", ("tests/test_reverse_image.py",)),
    ("startup_checks.py", ("tests/test_startup_checks.py",)),
    ("vercel.json", ("tests/test_vercel_env_normalize.py",)),
    ("scripts/verify_", ("tests/test_vercel_env_normalize.py", "tests/test_startup_checks.py")),
    ("templates/", ("tests/test_business_pages.py", "tests/test_welcome.py", "tests/test_auth_layout.py")),
    # static/ is covered by test_settings_persistence.js (Node); keep Python smoke via rg on "script"
    ("static/", ("tests/test_app.py",)),
]

SMOKE_TESTS = (
    "tests/test_startup_checks.py",
    "tests/test_feature_gates.py",
)


def _git_diff_names(base: str, head: str) -> list[str]:
    if not base or not head or set(base) == {"0"}:
        return []
    r = subprocess.run(
        ["git", "diff", "--name-only", base, head],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return []
    return [x.strip() for x in r.stdout.splitlines() if x.strip()]


def _fallback_diff_one_commit() -> list[str]:
    r = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return []
    return [x.strip() for x in r.stdout.splitlines() if x.strip()]


def _changed_files() -> list[str]:
    base = (os.environ.get("DIFF_BASE") or "").strip()
    head = (os.environ.get("DIFF_HEAD") or "").strip()
    # Invalid / force-push: before can be 40 zeros
    if base and head and not base.startswith("0000000") and base != "0" * 40:
        names = _git_diff_names(base, head)
        if names:
            return names
    return _fallback_diff_one_commit()


def _test_file_for_root_module(name: str) -> str | None:
    if not name.endswith(".py") or "/" in name:
        return None
    stem = Path(name).stem
    p = TESTS / f"test_{stem}.py"
    if p.is_file():
        return str(p.relative_to(ROOT)).replace("\\", "/")
    return None


def _tests_mentioning(token: str) -> list[str]:
    """Find tests whose text mentions *token* (route or module name). No ripgrep dependency."""
    if not token or len(token) < 2:
        return []
    out: list[str] = []
    pat = re.compile(re.escape(token), re.I)
    for p in sorted(TESTS.glob("test_*.py")):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if pat.search(text):
            out.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    return out


def _select_tests(changed: list[str]) -> tuple[str, list[str]]:
    """
    Return (mode, argv) where mode is "full" or "partial".
    For partial, argv is a list of test file paths to pass to pytest.
    """
    if (os.environ.get("RUN_FULL_TESTS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return "full", []
    if not changed:
        return "smoke", list(SMOKE_TESTS)

    norm = [c.replace("\\", "/") for c in changed]

    for f in norm:
        base = f.split("/")[-1] if "/" in f else f
        if base in FULL_SUITE_FILES or f in FULL_SUITE_FILES:
            return "full", []
        for pref in FULL_SUITE_PATH_PREFIXES:
            if f.startswith(pref) or f == pref:
                return "full", []

    if any(n == "app.py" or n.endswith("/app.py") for n in norm):
        return "full", []

    selected: set[str] = set()

    for f in norm:
        if f.startswith("tests/") and f.endswith(".py") and f != "tests/conftest.py":
            if (ROOT / f).is_file():
                selected.add(f)
            continue
        for prefix, tfiles in PATH_HINTS:
            if f.startswith(prefix) or f == prefix or (prefix.endswith("/") and f.startswith(prefix)):
                selected.update(tfiles)
        root_tf = _test_file_for_root_module(f)
        if root_tf:
            selected.add(root_tf)
        # Keyword: stem for single-file renames, last path segment
        stem = Path(f).stem
        for tok in (stem, Path(f).name.replace(".py", "")):
            selected.update(_tests_mentioning(tok))
        if "/" in f:
            selected.update(_tests_mentioning(f.split("/")[0]))

    # Drop non-Python test artifacts
    selected = {s for s in selected if s.endswith(".py") and (ROOT / s).is_file()}

    if not selected:
        return "smoke", list(SMOKE_TESTS)
    return "partial", sorted(selected)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print pytest command and exit 0 (do not run pytest).",
    )
    ap.add_argument(
        "--force-full",
        action="store_true",
        help="Always run the full test suite (e.g. local validation).",
    )
    args = ap.parse_args()
    if args.force_full:
        mode, files = "full", []
    else:
        mode, files = _select_tests(_changed_files())

    if mode == "full":
        cmd: list[str] = [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"]
        print("run_tests_for_changes: full suite (critical path or app.py)", file=sys.stderr)
    elif mode == "smoke":
        cmd = [sys.executable, "-m", "pytest", *files, "-v", "--tb=short"]
        print("run_tests_for_changes: smoke (no mapping)", file=sys.stderr)
    else:
        cmd = [sys.executable, "-m", "pytest", *files, "-v", "--tb=short"]
        print(f"run_tests_for_changes: partial ({len(files)} file(s))", file=sys.stderr)

    print(" ", " ".join(cmd), file=sys.stderr)
    if args.dry_run:
        return 0
    p = subprocess.run(cmd, cwd=ROOT)
    return p.returncode


if __name__ == "__main__":
    raise SystemExit(main())

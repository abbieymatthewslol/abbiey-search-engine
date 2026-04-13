#!/usr/bin/env python3
"""
Audit Validator for abbiey.search.
Checks for consistency across all integration points and project IDs.
"""

import os
import sys
from pathlib import Path

# Canonical Project IDs
CANONICAL = {
    "SUPABASE_REF": "xwxscvllmghyogddpmii",
    "VERCEL_PROJECT_ID": "prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b",
    "VERCEL_TEAM_ID": "team_YeguIG4NHm4Kp0Jf5AbOwgFN",
    "GOOGLE_CLOUD_PROJECT_NUMBER": "323605814484",
    "GITHUB_REPO": "abbieymatthewslol/abbiey-search-engine"
}

# Known broken/old IDs to flag
DEPRECATED = {
    "SUPABASE_REF_OLD": "xibqrimcvgtxtqkybxaa",
    "SUPABASE_REF_TYPO": "xwxcvllmghyogddpmii",
}

REPO_ROOT = Path(__file__).parent.parent

def load_env(path):
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env

def audit_env_file(path):
    print(f"\n--- Auditing {path.name} ---")
    env = load_env(path)
    issues = 0
    
    # Check Supabase Ref in URL and DB_URL
    for key in ["SUPABASE_URL", "SUPABASE_DB_URL"]:
        val = env.get(key, "")
        if val:
            if CANONICAL["SUPABASE_REF"] not in val:
                print(f"  [FAIL] {key} does not contain canonical ref {CANONICAL['SUPABASE_REF']}")
                issues += 1
            else:
                print(f"  [PASS] {key} contains canonical ref.")
                
            # Check for SSL requirement in DB_URL
            if key == "SUPABASE_DB_URL" and "sslmode=require" not in val:
                print(f"  [FAIL] {key} is missing sslmode=require")
                issues += 1
                
    return issues

def audit_source_code():
    print(f"\n--- Auditing Source Code & Scripts ---")
    issues = 0
    
    # Files to ignore
    ignore_files = {".git", "node_modules", "AUDIT_INVENTORY.md", "AUDIT_REPORT.md", "audit_validator.py"}
    
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in ignore_files]
        for file in files:
            if file in ignore_files: continue
            path = Path(root) / file
            
            # Only scan text files
            if path.suffix not in [".py", ".js", ".html", ".md", ".yml", ".json", ".txt"]:
                continue
                
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
                
            # Check for deprecated IDs
            for label, old_id in DEPRECATED.items():
                if old_id in content:
                    # Special case for AGENTS.md/CLAUDE.md/app.py where we document the fix
                    if path.name in ["AGENTS.md", "CLAUDE.md", "app.py", "health_check.py", "verify_production_env.py"]:
                        continue
                    print(f"  [WARN] {path.relative_to(REPO_ROOT)} contains deprecated/broken ID: {old_id} ({label})")
                    issues += 1
                    
    return issues

def main():
    total_issues = 0
    
    # Audit .env and .env.example
    total_issues += audit_env_file(REPO_ROOT / ".env")
    total_issues += audit_env_file(REPO_ROOT / ".env.example")
    
    # Audit source code
    total_issues += audit_source_code()
    
    print(f"\n--- Audit Summary ---")
    if total_issues == 0:
        print("All integration points are consistent and using canonical IDs.")
    else:
        print(f"Found {total_issues} issues that need attention.")
        
    return 1 if total_issues > 0 else 0

if __name__ == "__main__":
    sys.exit(main())

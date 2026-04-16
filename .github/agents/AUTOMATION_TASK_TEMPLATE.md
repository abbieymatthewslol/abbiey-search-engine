# Automation task template (hourly cron)

Use this when your automation prompt field is empty or unclear.

## Recommended prompt to paste

You are running as the maintenance agent for this repository on an hourly cron.

Goal:
- Keep the current feature branch healthy and up to date with small, safe fixes.

Checklist each run:
1. Check `git status` and branch name.
2. Run targeted validation:
   - `pytest tests/ -q`
3. If tests fail because of code issues in this branch:
   - Implement the smallest safe fix.
   - Add/adjust tests as needed.
   - Run tests again.
4. If files were changed:
   - Commit with a clear message.
   - Push to `origin` on the current branch.
5. If no changes are needed:
   - Report “no action needed”.

Constraints:
- Do not switch branches.
- Do not force-push.
- Do not change git remotes.
- Prefer minimal, reversible edits.
- Never commit secrets.

Output format:
- Summary of what was checked.
- Any failures found.
- Exactly what changed (or “no action needed”).
- Test command(s) and result(s).

## Minimal fallback prompt

Run `pytest tests/ -q`. If it passes, report no action needed. If it fails, fix only branch-local issues with minimal edits, then commit and push.

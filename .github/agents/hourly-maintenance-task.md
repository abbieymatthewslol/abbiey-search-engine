# Hourly Automation Task Definition (Fallback)

Use this task when a scheduled automation run is triggered and the user query is empty, placeholder, or otherwise non-actionable (for example: "idk what to put here").

## Objective

Keep repository health high with a safe, low-risk hourly maintenance pass that favors validation and small fixes.

## Required Steps (in order)

1. **Sync and inspect branch state**
   - Run `git status -sb`.
   - Confirm work happens on the current task branch (do not switch unless explicitly instructed).

2. **Run fast codebase checks**
   - Run `pytest tests/ -v`.
   - If tests fail, fix only clearly scoped regressions that can be resolved safely in this run.

3. **Run configuration sanity checks**
   - Run `python scripts/verify_production_env.py`.
   - Treat output as advisory unless strict mode is explicitly requested.

4. **Apply minimal safe maintenance**
   - Allowed: typo fixes, broken docs references, small defensive bug fixes, test stabilizations.
   - Not allowed: large refactors, framework swaps, risky dependency churn.

5. **Validate and ship**
   - Re-run impacted tests/checks.
   - Commit with a clear message.
   - Push to the current branch.

6. **Report outcome**
   - Summarize:
     - checks run and results,
     - files changed (if any),
     - residual risks or follow-ups.

## No-op Rule

If no safe improvements are identified and all checks pass:
- make no code changes,
- report a clean maintenance pass with evidence (commands + outcomes).

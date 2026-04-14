# Automation Task Template

Use this when an automation trigger runs but the task prompt is vague or empty.

## Copy/paste prompt

```md
Goal: <one specific outcome>

Context:
- Why this matters: <user impact or repo health impact>
- Scope: <files/folders allowed to change>
- Non-goals: <what should not be changed>

Definition of done:
1. <observable result #1>
2. <observable result #2>
3. Tests: <exact command(s) to run> and all pass
4. Git: commit + push changes to the active branch

Constraints:
- Keep changes minimal and production-safe
- Do not add secrets
- Update docs/tests affected by the change
```

## Good prompt examples

### 1) Bugfix

```md
Goal: Fix 500 error on /api/related when q is missing.

Context:
- Why this matters: endpoint crashes and breaks search UI suggestions
- Scope: app.py + tests/test_related_api.py
- Non-goals: no UI redesign, no dependency changes

Definition of done:
1. /api/related returns 400 JSON error when q is empty
2. Existing valid requests still return 200
3. Tests: pytest tests/test_related_api.py -v
4. Git: commit + push to current task branch

Constraints:
- Preserve current response schema for successful requests
- Keep patch focused on validation + tests
```

### 2) Feature

```md
Goal: Add a "Clear recent searches" action in the search history dropdown.

Context:
- Why this matters: users need one-click privacy cleanup
- Scope: templates/index.html, static/script.js, tests/test_settings_persistence.js (if impacted)
- Non-goals: no account-level sync changes

Definition of done:
1. Button is visible in search history UI
2. Clicking removes locally stored recent searches and refreshes the view
3. No console errors in normal usage flow
4. Git: commit + push to current task branch
```

### 3) Refactor

```md
Goal: Extract duplicated URL-normalization logic into one helper.

Context:
- Why this matters: reduce drift and simplify future bugfixes
- Scope: retrieval/* and app.py call sites only
- Non-goals: no ranking logic changes

Definition of done:
1. Duplicated normalization blocks are removed
2. Existing behavior is unchanged (same tests pass)
3. Tests: pytest tests/ -v
4. Git: commit + push to current task branch
```

### 4) Docs-only maintenance

```md
Goal: Update README deployment section to match current Supabase + Vercel flow.

Context:
- Why this matters: contributors follow README first and currently hit stale steps
- Scope: README.md and related docs only
- Non-goals: no code changes

Definition of done:
1. Steps reflect current required environment variables
2. Links point to existing files
3. Git: commit + push to current task branch
```

## Prompt quality checklist

Before running automation, verify the prompt answers all of these:

- Is there exactly one primary outcome?
- Is the scope explicit (which files/components can change)?
- Are non-goals listed?
- Are test/verification commands specified?
- Is "done" measurable with observable results?
- Does it clearly require commit + push on the active branch?

If any answer is "no", tighten the prompt before triggering automation.

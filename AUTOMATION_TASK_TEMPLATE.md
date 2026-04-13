# Automation Task Template

Use this template when creating cron/webhook/background automation requests for this repository.

## Copy/paste prompt

```md
Goal: <one clear objective>
Context:
- <issue/PR URL or internal note>
- <relevant files or subsystem>

Constraints:
- Keep changes scoped to <area>
- Do not modify <sensitive area>

Definition of done:
- <observable outcome 1>
- <observable outcome 2>

Verification:
- Run: <command 1>
- Run: <command 2>
- Confirm: <manual check>

Out of scope:
- <explicitly excluded work>
```

## Good prompt examples

### Example 1: Failing test triage

```md
Goal: Fix the current failing pytest test on master.
Context:
- CI run: <url>
- Suspect files: tests/test_search_api.py, app.py
Constraints:
- No UI/CSS changes.
Definition of done:
- pytest tests/test_search_api.py -v passes locally.
- No unrelated files changed.
Verification:
- Run: pytest tests/test_search_api.py -v
```

### Example 2: Docs-only maintenance

```md
Goal: Refresh deployment docs for current Supabase + Vercel flow.
Context:
- Files: README.md, CLAUDE.md, .github/PLATFORM_INTEGRATIONS.md
Constraints:
- Documentation only (no runtime code changes).
Definition of done:
- All three docs describe the same required env vars.
- Outdated steps are removed.
Verification:
- Manual diff review confirms consistency.
```

## Minimum quality bar

Avoid prompts like "idk what to put here." At minimum, always include:

1. A single concrete goal.
2. One or more files/systems in scope.
3. Clear done criteria that can be verified.

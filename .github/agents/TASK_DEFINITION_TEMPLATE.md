# Automation `user_query` Template

Use this when an automation trigger needs a concrete task.

## Quick format

```text
Goal: <what should be changed or verified>
Scope: <files/components to touch>
Acceptance criteria:
- <observable outcome 1>
- <observable outcome 2>
Validation:
- <exact command(s) to run>
Constraints:
- <anything to avoid, optional>
```

## Copy/paste examples

### 1) Fix a bug

```text
Goal: Fix the login redirect loop after successful Google OAuth.
Scope: app.py auth callback flow and templates/auth_confirm.html only.
Acceptance criteria:
- `/auth/confirm` returns users to `/profile` after successful sign-in.
- No redirect loop occurs for authenticated sessions.
Validation:
- pytest tests/test_auth.py -v
Constraints:
- Do not change database schema.
```

### 2) Add or adjust tests

```text
Goal: Add regression tests for Deep Web fallback behavior.
Scope: tests/test_deep_web.py and minimal app.py changes only if required.
Acceptance criteria:
- New tests cover Ahmia timeout and DDG onion fallback path.
- Existing deep web tests continue to pass.
Validation:
- pytest tests/test_deep_web.py -v
Constraints:
- Keep production behavior unchanged unless test exposes a bug.
```

### 3) Safe maintenance task (good for cron)

```text
Goal: Run test suite and fix any failing tests with minimal changes.
Scope: Only files needed to fix failures.
Acceptance criteria:
- `pytest tests/ -v` passes.
- Changes are limited to root cause fixes; no broad refactors.
Validation:
- pytest tests/ -v
Constraints:
- Do not add new dependencies unless required for a failing test fix.
```

### 4) Docs-only update

```text
Goal: Update README deployment section to match current Vercel + Supabase setup.
Scope: README.md and related docs only.
Acceptance criteria:
- Steps are accurate and internally consistent.
- No code files are changed.
Validation:
- Manual review for consistency against CLAUDE.md.
```

## If you are unsure what to ask for

Start with the "Safe maintenance task (good for cron)" example and adjust scope after the first run.

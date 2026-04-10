# Automation Task Template

Use this template in `user_query` for cron/webhook runs so the agent has a concrete objective.

## Copy/paste template

```md
Goal:
- <what outcome should be achieved?>

Scope:
- <which files, directories, or features are in scope?>
- <what is explicitly out of scope?>

Definition of done:
- [ ] <how to verify the change worked?>
- [ ] <tests/commands that must pass>

Constraints:
- <security, performance, compatibility, or style constraints>

Deliverables:
- <expected code/docs/test changes>
```

## Good examples

### Example 1: bug fix

```md
Goal:
- Fix the `/api/preview` redirect handling bug for private IP destinations.

Scope:
- `app.py` preview fetch logic and related tests only.
- Out of scope: UI/layout changes.

Definition of done:
- [ ] Private-network redirect targets are blocked.
- [ ] `python3 -m pytest tests/test_app.py::TestPreviewSsrfRedirect -v` passes.

Constraints:
- Keep current public API response shape.
- Do not add new dependencies.

Deliverables:
- Code fix + focused test updates.
```

### Example 2: maintenance pass

```md
Goal:
- Run a repository health pass and fix the first failing test.

Scope:
- Test-related fixes only.
- Out of scope: feature development.

Definition of done:
- [ ] `python3 -m pytest tests/ -v` finishes cleanly.
- [ ] Changes are committed with a descriptive message.

Constraints:
- Prefer minimal, low-risk changes.

Deliverables:
- Small fix PR with test evidence.
```

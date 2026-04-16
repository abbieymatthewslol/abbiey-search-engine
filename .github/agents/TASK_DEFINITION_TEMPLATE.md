# Task Definition Template for Repository Agents

Copy/paste this when opening an issue, triggering an automation run, or assigning a background task.

```md
## Task
Short imperative summary (example: "Harden auth callback error handling").

## Why
What user or reliability problem this solves.

## Constraints
- Keep changes minimal and safe.
- Do not introduce new dependencies unless necessary.
- Keep branch/commit scope focused.

## Files to Touch
- `app.py`
- `tests/test_auth.py`
- `README.md`

## Acceptance Criteria
- [ ] Behavior is correct for normal and edge cases.
- [ ] Tests were added/updated for changed behavior.
- [ ] Relevant docs were updated if user-facing behavior changed.

## Validation
- Run:
  - `pytest tests/ -v`
- Include command output summary in final report.

## Deliverables
- Commit message format: `fix(<area>): <summary>` (or `docs:` / `test:` when appropriate)
- Final report includes:
  - what changed
  - test evidence
  - risks or follow-ups
```

## Good Prompt Examples

### 1) Bug fix

```md
Task: Fix weather card not rendering for "weather <city>" queries with extra spaces.
Files to touch: `app.py`, `tests/test_weather.py`
Acceptance criteria: weather card appears, no regression to non-weather searches.
Validation: `pytest tests/test_weather.py -v`
```

### 2) Docs-only safety task

```md
Task: Update README deployment notes to match current Supabase pooler requirement.
Files to touch: `README.md`, `CLAUDE.md`
Acceptance criteria: no stale env var names; examples are copy/paste safe.
Validation: manual doc review for consistency across both files.
```

## Blank/Vague Prompt Fallback

If the incoming task is blank or vague (for example, "idk what to put here"):
1. First improve automation guidance docs/templates only.
2. Avoid speculative product features.
3. Keep changes low-risk and easy to review.

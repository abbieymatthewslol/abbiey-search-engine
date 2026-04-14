# Automation Task Template

Use this when creating cron/manual automation runs so the agent receives a clear, actionable task.

## Copy/paste prompt template

```md
Goal:
- <what outcome should exist after this run?>

Context:
- <why this matters, links to issue/PR, affected feature>

Scope:
- In scope: <files/areas that may change>
- Out of scope: <what must not change>

Constraints:
- <security/performance/compatibility requirements>
- <branch, environment, or deployment constraints>

Validation:
- Run: <exact commands to verify success>
- Expect: <what output/behavior indicates success>

Deliverable:
- <what to commit (code/docs/tests) and expected summary>
```

## Example prompts

### 1) Bug fix

```md
Goal:
- Fix the weather card failing for city names with spaces.

Context:
- Regression reported in issue #123. Failing path is `/api/entity`.

Scope:
- In scope: `entity_parser.py`, related tests.
- Out of scope: UI redesign.

Constraints:
- Do not add new dependencies.
- Keep existing API shape unchanged.

Validation:
- Run: `pytest tests/test_entity_parser.py -v`
- Expect: weather-related tests pass and no new failures.

Deliverable:
- Commit bug fix + tests and summarize root cause.
```

### 2) Maintenance/docs

```md
Goal:
- Refresh onboarding docs for local Supabase setup.

Context:
- New contributors miss required env vars.

Scope:
- In scope: `README.md`, `CLAUDE.md`.
- Out of scope: application code changes.

Constraints:
- Keep guidance consistent with current scripts in `scripts/`.

Validation:
- Run: manually verify commands/paths in docs match repository.
- Expect: instructions are accurate and non-contradictory.

Deliverable:
- Commit docs-only update with concise change summary.
```

## Prompt quality checklist

Before triggering automation, ensure the prompt answers:

- What should be different when the run finishes?
- Which files or subsystems can change?
- What must not change?
- How should success be verified?
- What artifact is expected (tests, docs, bug fix, etc.)?

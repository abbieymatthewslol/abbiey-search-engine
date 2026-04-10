# Automation Task Prompt Template

Use this template when configuring a cron/webhook automation so the agent has a concrete goal.

## What to put in `user_query`

Copy/paste and fill this in:

```text
Goal:
- <single clear objective, e.g. "review open PR #123 for regressions">

Scope:
- Files/areas allowed: <paths or "entire repo">
- Files/areas excluded: <optional>

Constraints:
- Tests to run: <exact commands or "none">
- Do not change: <optional guardrails>

Definition of done:
- <observable completion criteria>
- <what to report back>
```

## Good examples

1) **Dependency hygiene**

```text
Goal:
- Audit Python dependencies for outdated or vulnerable packages and submit safe patch updates.

Scope:
- Files/areas allowed: requirements.txt, requirements-dev.txt, scripts/
- Files/areas excluded: app runtime behavior changes

Constraints:
- Tests to run: pytest tests/test_app.py -q
- Do not change: frontend templates/static files

Definition of done:
- Dependency updates committed and pushed
- Test output summarized, including any failures
```

2) **Test reliability**

```text
Goal:
- Identify and fix one flaky test in tests/ if reproducible.

Scope:
- Files/areas allowed: tests/, minimal production code needed for deterministic behavior
- Files/areas excluded: unrelated refactors

Constraints:
- Tests to run: pytest tests/ -q
- Do not change: deployment/infrastructure config

Definition of done:
- Root cause explained
- Fix committed and pushed (or clear repro notes if not fixable safely)
```

## Avoid

- Placeholder prompts like "idk what to put here"
- Multiple unrelated goals in one run
- Missing validation steps

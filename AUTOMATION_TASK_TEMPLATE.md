# Automation Task Template

Use this template when triggering an automation run so the agent gets a concrete, testable objective.

## Copy/paste template

```md
## Goal
<One sentence describing the outcome you want.>

## Scope
- In scope: <files/features allowed to change>
- Out of scope: <what must not change>

## Required changes
1. <specific change #1>
2. <specific change #2>

## Acceptance criteria
- [ ] <observable behavior or output>
- [ ] <tests to run and pass>
- [ ] <docs or follow-up updates required>

## Constraints
- Branch: <branch name, if fixed>
- Avoid: <risky operations to avoid>
- Dependencies: <allowed/forbidden dependency changes>

## Verification
- Run: `<exact commands>`
- Expect: <key success signals>
```

## Good prompt example

```md
## Goal
Add a compact weather card to the search results for `weather <city>` queries.

## Scope
- In scope: `app.py`, `templates/index.html`, `static/style.css`, `tests/`
- Out of scope: auth flows and unrelated UI components

## Required changes
1. Render a weather card only when weather entity detection succeeds.
2. Show city, current temperature, and 3-day forecast summary.
3. Add tests for the card rendering condition.

## Acceptance criteria
- [ ] Query `weather london` shows the card with current conditions.
- [ ] Non-weather queries do not render the weather card.
- [ ] `pytest tests/ -v` passes.

## Verification
- Run: `pytest tests/ -v`
- Expect: all tests pass and weather card behavior matches criteria
```

## Minimal prompt checklist

Before sending an automation prompt, confirm it answers:

1. What should change?
2. Where should it change?
3. How will we verify it worked?

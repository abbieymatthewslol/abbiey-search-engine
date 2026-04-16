# Automation Task Template

Use this when configuring a cron/webhook/manual automation run for this repo.

## Copy/paste prompt skeleton

```md
Goal:
- <one sentence describing the outcome>

Scope:
- In scope: <files/areas the agent may change>
- Out of scope: <what the agent must not change>

Acceptance criteria:
1. <observable result #1>
2. <observable result #2>
3. Tests/checks run: <exact command(s)>

Output requirements:
- Commit changes to the current task branch
- Push branch to origin
- Open or update a PR with a concise summary
```

## Good prompt examples

### Example: bug fix

```md
Goal:
- Fix broken weather card rendering when forecast API returns partial fields.

Scope:
- In scope: `app.py`, `templates/index.html`, `tests/test_weather.py`
- Out of scope: unrelated UI refactors

Acceptance criteria:
1. Missing forecast fields do not crash rendering.
2. Weather card shows fallback values instead of blank cards.
3. `pytest tests/test_weather.py -v` passes.

Output requirements:
- Commit, push, and open/update PR.
```

### Example: docs-only maintenance

```md
Goal:
- Improve contributor docs for local Supabase setup.

Scope:
- In scope: `README.md`, `CLAUDE.md`
- Out of scope: runtime code changes

Acceptance criteria:
1. README includes a short local setup checklist.
2. CLAUDE.md links to the same checklist.
3. No app code files changed.
```

## Avoid vague prompts

Bad:
- `idk what to put here`
- `fix stuff`

Better:

```md
Goal:
- Run a low-risk repo maintenance pass.

Scope:
- In scope: missing docs/templates for automation prompts
- Out of scope: app logic changes

Acceptance criteria:
1. Automation task templates exist and are linked from README.
2. Agent instructions include fallback behavior for blank/vague trigger text.
3. Change is docs-only.
```

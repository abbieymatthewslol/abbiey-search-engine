# Automation Task Template

Use this template when setting `user_query` for scheduled or webhook-triggered automations.

## Copy/Paste Template

```md
## Objective
<What should be improved or fixed?>

## Scope
- In scope:
  - <file/area>
  - <file/area>
- Out of scope:
  - <explicit exclusions>

## Requirements
- <behavioral requirement 1>
- <behavioral requirement 2>

## Validation
- Run: `<command>`
- Confirm: `<expected output or behavior>`

## Deliverables
- [ ] Code/docs updated
- [ ] Tests added/updated (if needed)
- [ ] Commit + push to current task branch
```

## Good Prompt Examples

### 1) Bug Fix

```md
Objective: Fix keyboard navigation skipping the first result in `templates/index.html`.
Scope: Only `templates/index.html` and `static/script.js`.
Requirements:
- `j/k` should always highlight a valid first item.
- Do not change mouse hover behavior.
Validation:
- Run: `pytest tests/ -v`
- Manual check: open app and verify first result can be focused with `j`.
```

### 2) Docs Improvement

```md
Objective: Document how to verify Supabase DB connectivity in local dev.
Scope: `README.md` and `scripts/verify_supabase_connection.py` docstring only.
Requirements:
- Include exact command and expected success log line.
- Keep docs consistent with `CLAUDE.md`.
Validation:
- Run: `python scripts/verify_supabase_connection.py`
```

## Anti-Patterns (Avoid These)

- "idk what to put here"
- "fix stuff"
- "make it better"
- Missing validation commands
- No scope boundaries

## Minimum Bar for Automation Prompts

Before saving a prompt, ensure it has:

1. A clear objective
2. Explicit scope
3. At least one concrete validation step

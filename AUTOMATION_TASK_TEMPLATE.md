# Automation Task Template

Use this template when configuring a cron/webhook automation prompt. It prevents empty or vague requests (for example, "idk what to put here") and gives the agent clear acceptance criteria.

## Copy/paste prompt

```md
Objective:
- <one concrete outcome>

Scope:
- <files/components allowed to change>
- <explicitly out-of-scope items>

Acceptance criteria:
- <observable behavior or output 1>
- <observable behavior or output 2>

Validation:
- Run: <exact command(s)>
- Expect: <what should pass or be true>

Deliverables:
- <code/docs/tests expected>
- <whether commit + push is required>
```

## Good examples

### Example: bug fix

```md
Objective:
- Fix keyboard navigation so pressing `j` highlights the next result card.

Scope:
- Update only `static/script.js` and related tests.
- Do not change HTML structure or CSS.

Acceptance criteria:
- `j` moves selection to the next result card.
- Selection wraps from last card back to first card.
- Existing `k` behavior remains unchanged.

Validation:
- Run: `pytest tests/ -v`
- Expect: all tests pass.

Deliverables:
- Code fix + tests.
- Commit and push to the current feature branch.
```

### Example: docs maintenance

```md
Objective:
- Add missing setup notes for local Supabase configuration.

Scope:
- Update `README.md` and `CLAUDE.md` only.
- No application code changes.

Acceptance criteria:
- README links to the exact Supabase setup section.
- Instructions include required env var names.

Validation:
- Manually verify both links and env var names are correct.

Deliverables:
- Docs-only commit pushed to branch.
```

## Quality bar for automation prompts

- Be specific about **what to change** and **what not to change**.
- Include at least one executable validation step when code changes are expected.
- Prefer measurable acceptance criteria over broad requests like "improve app."
- If you only want analysis, state that explicitly ("no file changes").

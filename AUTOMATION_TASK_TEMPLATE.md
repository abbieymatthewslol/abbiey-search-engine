# Automation Task Template

Use this template when triggering an automated coding run. It helps the agent produce predictable, useful changes.

## Copy/paste prompt

```md
Goal
- [What should change?]

Context
- [Relevant files, links, or background]
- [Known constraints]

Scope
- In scope: [what to touch]
- Out of scope: [what not to touch]

Acceptance criteria
- [ ] [Behavior/result to verify]
- [ ] [Tests/checks that must pass]
- [ ] [Docs/changelog update if needed]

Output expectations
- Branch: [optional]
- Commit style: [optional]
- PR notes: [optional]
```

## Good examples

### Example 1: Bug fix

```md
Goal
- Fix the `/api/related` endpoint returning duplicate suggestions.

Context
- Investigate `app.py` and any helper functions used for related search formatting.
- Keep response shape backward-compatible.

Scope
- In scope: deduplication logic, related tests.
- Out of scope: ranking changes.

Acceptance criteria
- [ ] API no longer returns duplicate strings for identical normalized values.
- [ ] Existing related-search tests pass.
- [ ] Add/adjust tests covering duplicate inputs.
```

### Example 2: UI improvement

```md
Goal
- Add a keyboard shortcut hint to the search results help popover.

Context
- Frontend code is in `static/script.js` and `templates/index.html`.
- Preserve CSP nonce usage on any inline script changes.

Scope
- In scope: help popover content and any styles required.
- Out of scope: remapping keyboard shortcuts.

Acceptance criteria
- [ ] Hint is visible in light and dark themes.
- [ ] No CSP regressions introduced.
- [ ] Relevant frontend tests/manual checks documented.
```

## What to avoid

- Vague prompts like “fix stuff” or “make it better”.
- Missing acceptance criteria.
- Mixing unrelated goals in one run.
- Requesting risky refactors without boundaries.

# Automation Task Template

Use this template when triggering Cursor automation so the agent has a concrete, testable objective.

## Copy/paste template

```md
Goal:
- <What outcome do you want?>

Scope:
- <Files/components to touch>
- <What should NOT be changed>

Constraints:
- <Branch or deployment constraints>
- <Performance/security requirements>

Acceptance criteria:
- [ ] <Observable condition 1>
- [ ] <Observable condition 2>

Verification:
- Run: <exact command(s)>
- Expected: <exact success signal>

Deliverable:
- <Commit message format / summary expectations>
```

## Good examples

### Example 1: bug fix

```md
Goal:
- Fix empty-state rendering bug in search results.

Scope:
- Touch `templates/index.html` and `static/script.js` only.
- Do not change API routes or DB schema.

Acceptance criteria:
- [ ] Empty query shows friendly empty-state card.
- [ ] Existing result rendering remains unchanged.

Verification:
- Run: `pytest tests/test_app.py -k empty_state -v`
- Expected: test passes with no new failures.
```

### Example 2: docs-only task

```md
Goal:
- Document how to run production readiness checks locally.

Scope:
- Update `README.md` only.

Acceptance criteria:
- [ ] README includes exact command and expected output section.

Verification:
- Run: `python3 scripts/verify_production_env.py`
- Expected: command runs and output is referenced accurately.
```

## Avoid vague prompts

Avoid prompts like:
- "idk what to put here"
- "just improve stuff"

These force the agent to guess intent and increase the risk of irrelevant changes.

## Automation Task Prompt Template

Use this template when creating or updating an automation prompt.

```
Goal:
- <what outcome should be delivered?>

Scope:
- In scope: <files/features allowed to change>
- Out of scope: <explicit exclusions>

Constraints:
- <performance, security, style, deployment, or dependency constraints>

Acceptance criteria:
- [ ] <observable behavior change>
- [ ] <tests/docs updated as needed>
- [ ] <no regressions in related flows>

Validation:
- Run: <commands, e.g. pytest tests/ -v>
- Expected: <key pass criteria>

Deliverable:
- <commit summary or artifact expected from the run>
```

## Quick Prompt Examples

### 1) Bug fix
```
Goal:
- Fix calculator result formatting for scientific notation in search cards.

Scope:
- In scope: app.py, static/script.js, tests/test_calculator.py
- Out of scope: unrelated UI refactors

Acceptance criteria:
- [ ] `1e6` displays as `1,000,000`
- [ ] Existing calculator tests pass
- [ ] New regression test is added

Validation:
- Run: pytest tests/test_calculator.py -v
```

### 2) Docs-only change
```
Goal:
- Document CSP nonce requirements for inline scripts.

Scope:
- In scope: README.md, CLAUDE.md
- Out of scope: runtime code changes

Acceptance criteria:
- [ ] README has CSP nonce section with example snippet
- [ ] Guidance matches current app behavior
```

### 3) Maintenance sweep
```
Goal:
- Run the retrieval test suite and fix failing assertions.

Scope:
- In scope: retrieval/*.py, tests/test_retrieval.py
- Out of scope: auth, UI templates

Acceptance criteria:
- [ ] `pytest tests/test_retrieval.py -v` passes
- [ ] Any behavior changes are covered by tests
```

## Minimal Prompt (if you are unsure)

If you are not sure what to request, paste this:

```
Goal:
- Perform a docs-only repository hygiene update that improves contributor clarity.

Scope:
- In scope: README.md and one new markdown guide if needed
- Out of scope: application code, dependencies, deployment config

Acceptance criteria:
- [ ] Changes are small, accurate, and actionable
- [ ] README links to the new/updated guide
```

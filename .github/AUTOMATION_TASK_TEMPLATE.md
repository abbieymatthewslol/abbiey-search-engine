# Automation Task Definition Template

Use this when a scheduled or manual automation run needs a clear objective.

## Copy/paste skeleton

```md
<user_query>
Goal: <one sentence objective>

Context:
- Why this matters: <impact or pain point>
- Area(s): <files, folders, systems>

Constraints:
- Do not: <anything to avoid>
- Must preserve: <important behavior>

Definition of done:
- [ ] Code/docs updated
- [ ] Tests added/updated (if applicable)
- [ ] Verification command(s) run and results reported
- [ ] Changes committed and pushed to the current feature branch

Verification:
- Run: <exact command 1>
- Run: <exact command 2>
```

## Good examples

### Example 1: Failing tests triage

```md
<user_query>
Goal: Make the test suite pass on the current branch.

Context:
- Why this matters: CI is red and blocking merges.
- Area(s): tests/, app.py, retrieval/

Constraints:
- Do not remove tests to make CI green.
- Must preserve existing API response formats.

Definition of done:
- [ ] Root cause identified and fixed
- [ ] Relevant tests updated (only if behavior intentionally changed)
- [ ] `pytest tests/ -v` passes locally
- [ ] Commit + push completed

Verification:
- Run: pytest tests/ -v
```

### Example 2: Small feature addition

```md
<user_query>
Goal: Add a keyboard shortcut (`/`) to focus the search input.

Context:
- Why this matters: Faster keyboard navigation.
- Area(s): templates/index.html, static/script.js, tests/

Constraints:
- Do not break existing shortcuts (j/k, arrow keys, esc).
- Must preserve CSP nonce usage for inline scripts.

Definition of done:
- [ ] Shortcut implemented and documented in code comments if non-obvious
- [ ] Tests added/updated
- [ ] Manual verification steps provided
- [ ] Commit + push completed

Verification:
- Run: pytest tests/ -v
```

### Example 3: Dependency/security maintenance

```md
<user_query>
Goal: Upgrade vulnerable dependency versions without changing public behavior.

Context:
- Why this matters: Security and maintenance.
- Area(s): requirements.txt, lock/config files, affected imports

Constraints:
- Do not introduce breaking API changes.
- Must keep app startup and core search routes functional.

Definition of done:
- [ ] Dependencies upgraded to safe/latest compatible versions
- [ ] App imports and tests pass
- [ ] Any migration notes documented
- [ ] Commit + push completed

Verification:
- Run: pytest tests/ -v
- Run: python app.py (confirm startup logs)
```

## Minimum useful query (if you are in a hurry)

```md
<user_query>
Goal: <specific change>
Definition of done:
- [ ] Implemented
- [ ] Verified with: <command>
- [ ] Committed and pushed
```

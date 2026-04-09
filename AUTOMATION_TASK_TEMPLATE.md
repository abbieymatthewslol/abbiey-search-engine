# Automation Task Template

Use this when a scheduled run (or any automation trigger) asks for a task description.

## Quick copy/paste template

```text
Goal:
- <One clear objective>

Why:
- <Why this run should do this now>

Scope:
- In scope: <files/systems that may change>
- Out of scope: <what not to touch>

Constraints:
- Keep changes minimal and low risk
- Do not change production secrets or external service settings
- Run relevant tests/checks for touched code

Definition of done:
- [ ] Code/docs updated
- [ ] Relevant tests/checks run
- [ ] Changes committed and pushed
- [ ] Short summary of what changed and verification results
```

## Good examples

### Example 1 — health check and small fixes

```text
Goal:
- Run the Python and JS tests. If a test fails, fix only the failing issue.

Why:
- Keep main branch healthy for deployment.

Scope:
- In scope: tests/, app.py, static/script.js, templates/
- Out of scope: payment flows and auth provider configuration unless directly needed by failing tests

Constraints:
- Prefer the smallest safe fix.
- Do not refactor unrelated areas.

Definition of done:
- Tests pass locally.
- Fix is committed with a descriptive message.
```

### Example 2 — documentation maintenance

```text
Goal:
- Update docs that are out of sync with current environment variables and startup steps.

Why:
- Reduce setup friction for contributors.

Scope:
- In scope: README.md, project-index.md, .env.example
- Out of scope: runtime behavior changes

Definition of done:
- Docs are internally consistent.
- No code-path behavior changes.
- Changes committed and pushed.
```

### Example 3 — dependency patch run

```text
Goal:
- Upgrade one outdated dependency to the latest compatible version and fix related tests.

Why:
- Reduce security and maintenance risk.

Scope:
- In scope: dependency manifest + directly impacted code/tests
- Out of scope: broad framework migrations

Definition of done:
- Dependency upgraded.
- Relevant tests pass.
- Changelog note added if needed.
```

## Anti-patterns to avoid

- "Fix everything."
- "Refactor the app."
- "Improve performance" (without a measurable target).
- Missing scope or definition of done.

Keep tasks concrete, bounded, and verifiable.

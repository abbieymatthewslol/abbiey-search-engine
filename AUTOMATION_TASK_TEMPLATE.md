# Automation Task Template (Quick Start)

Use this when defining cron/webhook/background automation work in this repo.

## Copy/paste template

```md
## Objective
<One specific outcome. Example: "Stabilize flaky tests in feedback rerank coverage.">

## Scope
- In scope:
  - <files/modules allowed to change>
- Out of scope:
  - <what must not change>

## Constraints
- Keep changes minimal and production-safe.
- Do not add secrets or change deployment targets.
- Prefer docs/tests updates when task definition is ambiguous.

## Validation
- Run: <exact command(s), for example `pytest tests/test_feedback_rerank.py -v`>
- Confirm: <observable behavior or assertion>

## Acceptance Criteria
- [ ] Objective is met with a measurable result.
- [ ] Relevant tests/checks pass.
- [ ] Docs updated if behavior/process changed.
```

## Good examples

### 1) Bug fix

```md
## Objective
Fix CSP nonce regression for inline scripts in `templates/index.html`.

## Scope
- In scope:
  - `templates/index.html`
  - CSP-related tests under `tests/`
- Out of scope:
  - Styling or unrelated JS refactors

## Validation
- Run: `pytest tests/ -k csp -v`
- Confirm: every inline `<script>` in modified templates includes `nonce="{{ csp_nonce }}"`

## Acceptance Criteria
- [ ] CSP tests pass.
- [ ] No inline script without nonce remains in touched template.
```

### 2) Maintenance/docs fallback for vague prompts

```md
## Objective
Improve automation task templates so future runs include actionable prompts.

## Scope
- In scope:
  - `AUTOMATION_TASK_TEMPLATE.md`
  - `.github/agents/TASK_DEFINITION_TEMPLATE.md`
  - `README.md` automation pointer section
- Out of scope:
  - Product feature changes

## Validation
- Confirm templates include at least one bug-fix example and one docs-only example with acceptance criteria.

## Acceptance Criteria
- [ ] Both templates exist and are discoverable from README.
- [ ] Examples contain explicit validation commands or checks.
```

## Anti-patterns to avoid

- "Improve app" (too broad, no measurable end state)
- "Fix bugs" (no target behavior, no files/commands)
- Empty placeholders like "idk what to put here"

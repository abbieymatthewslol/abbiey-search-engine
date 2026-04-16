# Automation Task Template

Use this when a trigger runs but the task text is missing, vague, or placeholder.

## Objective
State one concrete goal in one sentence.

Example:
- Improve reliability by fixing one flaky test in `tests/` without changing product behavior.

## Scope
- In scope:
  - Files/components that may be edited.
- Out of scope:
  - Large refactors, new frameworks, or unrelated feature work.

## Constraints
- Keep changes minimal and safe.
- Do not commit secrets.
- Update docs/tests when behavior changes.

## Acceptance Criteria
- [ ] Change is small and clearly explained.
- [ ] Relevant tests pass locally (or a clear reason is documented).
- [ ] `git status` is clean after commit.

## Deliverables
- Brief summary of what changed.
- Commands run for verification.
- Any follow-up risk or TODO notes.

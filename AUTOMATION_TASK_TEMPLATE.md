# Automation Task Template

Use this template when an automated run (cron, webhook, scheduled workflow)
starts without a clear engineering request.

## 1) Context

- Trigger source: `<cron | webhook | manual>`
- Trigger metadata: `<timestamp, automation id, link to run>`
- Related issue/PR (if any): `<url or N/A>`

## 2) Problem Statement

Describe the concrete problem in one to three sentences.

Example:
"The automation run started with an empty prompt, so no scoped engineering
goal is defined. Without a task definition, changes risk being random and
hard to review."

## 3) Goal

State one primary, verifiable goal.

Example:
"Add or update documentation that captures how to provide actionable
automation prompts and acceptance criteria."

## 4) Constraints

- Keep changes low risk unless explicitly requested otherwise.
- Prefer docs-only improvements when requirements are undefined.
- Do not broaden scope beyond the stated goal.

## 5) Deliverables

List exact outputs.

- `<file path>` updated with `<what changed>`
- `<file path>` added with `<what changed>`

## 6) Acceptance Criteria

Use checkboxes so completion is unambiguous.

- [ ] Changes are directly tied to the stated goal.
- [ ] Modified docs are accurate for current repository workflows.
- [ ] No unrelated files were changed.
- [ ] `git status` is clean after commit.

## 7) Validation

Document how the change was verified.

- Commands run: `<e.g., rg pattern README.md>`
- Manual checks: `<what was reviewed>`

## 8) Commit Message

Provide a scoped commit subject.

Example:
`docs: add automation task template for undefined prompts`

## 9) Optional Follow-ups

List only non-blocking items discovered during the task.

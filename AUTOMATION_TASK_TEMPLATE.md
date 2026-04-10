# Automation Task Definition Template

Use this template when an automation run has an empty, unclear, or placeholder
task prompt.

## 1) Objective

Describe the specific outcome in one sentence.

Example:
`Add backend support for bookmarking search results with tests.`

## 2) Scope

List exactly what should be changed.

- Files or folders likely involved
- In-scope behavior changes
- Out-of-scope items (to avoid scope creep)

## 3) Constraints

Include guardrails the agent must follow.

- Branch to work on
- Dependencies allowed or forbidden
- Performance/security/privacy requirements
- Any deployment or environment limits

## 4) Verification

Define how to prove the task is complete.

- Tests to run (unit/integration/manual)
- Commands to execute
- Expected outputs or pass criteria

## 5) Definition of Done

Use a short checklist.

- [ ] Code and docs updated
- [ ] Tests pass
- [ ] Changes committed and pushed to the correct branch
- [ ] PR opened/updated with summary

## 6) Ready-to-Use Prompt Skeleton

Copy/paste and fill this into the automation query:

```text
Goal:
<what should be built/fixed>

Scope:
- In: <files/features>
- Out: <what not to change>

Constraints:
- Branch: <branch name>
- Requirements: <security/perf/privacy/etc>

Verification:
- Run: <commands>
- Expect: <pass criteria>

Done when:
- <check 1>
- <check 2>
- <check 3>
```

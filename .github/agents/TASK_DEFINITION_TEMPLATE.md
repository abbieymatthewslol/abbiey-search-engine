# Agent Task Definition Template

Use this for scheduled/background agents so each run has clear intent and measurable completion criteria.

## 1) Objective

- Primary objective:
- Why this objective matters:

## 2) Inputs and References

- Trigger source (cron/webhook/manual):
- Related issue/PR:
- Logs or failing checks:
- Relevant files/modules:

## 3) Guardrails

- Allowed changes:
- Forbidden changes:
- Risk tolerance (low/medium/high):
- Deployment constraints:

## 4) Required Steps

1. Gather context from referenced files and current git state.
2. Implement minimal safe changes.
3. Run relevant verification commands.
4. Commit and push with a descriptive message.
5. Report outcomes and residual risks.

## 5) Acceptance Criteria

- [ ] Requirement 1:
- [ ] Requirement 2:
- [ ] Verification output included
- [ ] No unrelated files changed

## 6) Output Format

- Summary:
- Files changed:
- Validation run:
- Follow-ups:

---

## Ready-to-use Example (Docs Repair)

```md
Objective:
- Restore missing automation task guidance and ensure README links are valid.

Inputs:
- README.md
- AUTOMATION_TASK_TEMPLATE.md
- .github/agents/my-agent.agent.md

Guardrails:
- Docs-only changes
- No runtime behavior changes

Acceptance Criteria:
- [ ] README links to both automation templates
- [ ] Fallback behavior for vague prompts is documented
- [ ] Changes committed and pushed
```

## Fallback for Blank/Vague Prompt Text

If task text is blank or vague (e.g. "idk what to put here"), do this by default:

1. Verify automation templates and README pointers exist.
2. Repair missing or stale guidance in docs.
3. Avoid speculative feature implementation.

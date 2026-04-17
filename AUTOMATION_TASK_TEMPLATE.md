# Automation Task Template

Use this when creating Cursor automation prompts for cron/webhook runs.

## Copy/Paste Template

```md
Goal:
- [What should be improved, fixed, or verified?]

Context:
- [Why this task matters now]
- [Links to issue/PR/logs, if any]

Scope:
- In scope: [files/systems allowed to change]
- Out of scope: [what must not change]

Acceptance Criteria:
- [ ] [observable outcome #1]
- [ ] [observable outcome #2]
- [ ] Tests/checks run and reported

Constraints:
- Keep changes low risk
- Preserve existing behavior unless explicitly requested
- Do not add secrets or change deployment targets
```

## Example: Hourly Repo Health Check

```md
Goal:
- Run lightweight repo health checks and fix docs drift if found.

Scope:
- In scope: README + automation templates + small docs fixes
- Out of scope: feature work, refactors, dependency upgrades

Acceptance Criteria:
- [ ] Automation/task template docs exist and are internally consistent
- [ ] Any docs-only fixes are committed and pushed
- [ ] Final report includes what changed (or "no changes needed")
```

## If You Are Unsure What To Put

Do not leave the prompt blank. Use this minimum task:

```md
Validate automation guidance docs and repair any missing templates or broken references.
```

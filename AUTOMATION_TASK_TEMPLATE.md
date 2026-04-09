# Automation Task Template

Use this file when the automation prompt is blank or unclear.

## Copy/Paste Prompt (default)

```text
Run a low-risk maintenance pass for this repository.

Goals:
1) Validate repository health with lightweight checks.
2) If you find issues, apply the smallest safe fix.
3) If no code changes are needed, report findings clearly and stop.

Required steps:
- Check git status and current branch.
- Run: python scripts/verify_production_env.py
- Run targeted tests only if you changed code.
- Summarize results (what ran, what passed/failed, what changed).

Change policy:
- Prefer docs-only or minimal fixes when prompt scope is ambiguous.
- Do not perform broad refactors.
```

## Example Prompts

### 1) Quick health check

```text
Run the default low-risk maintenance pass from AUTOMATION_TASK_TEMPLATE.md.
If everything is healthy, make no code changes and return a short report.
```

### 2) Docs cleanup only

```text
Review README, CLAUDE.md, and AGENTS.md for stale setup instructions.
Make docs-only corrections if needed, then summarize edits.
```

### 3) Test triage

```text
Run pytest tests/ -v. If failures are reproducible and localized, fix one small issue and add/adjust a focused test.
Avoid sweeping behavior changes.
```

## Success Criteria

- Prompt is explicit about scope.
- Steps are executable without human follow-up.
- Output includes concrete evidence (commands run + outcomes).

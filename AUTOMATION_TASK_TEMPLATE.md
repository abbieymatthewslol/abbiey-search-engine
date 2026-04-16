# Automation Task Template

Use this when creating cron/webhook tasks for this repository.

## Quick Prompt (copy/paste)

```text
Goal: <one concrete outcome>
Scope: <files/systems allowed to change>
Constraints: <what must not change>
Done when:
- <observable acceptance criterion 1>
- <observable acceptance criterion 2>
Validation:
- <command 1>
- <command 2>
```

## Examples

### 1) Docs-only maintenance

```text
Goal: Improve automation documentation for blank trigger prompts.
Scope: README.md and .github/agents/*.md only.
Constraints: No Python/JS code changes.
Done when:
- README includes an Automation section with links to prompt templates.
- Agent guidance includes a blank-prompt fallback policy.
Validation:
- rg "## Automation|blank|fallback" README.md .github/agents/*.md
- git diff --name-only
```

### 2) Safe reliability fix

```text
Goal: Stabilize one flaky test without changing product behavior.
Scope: tests/ plus minimal production code only if required.
Constraints: Keep behavior equivalent for end users.
Done when:
- Failing test is deterministic locally.
- Added/updated assertion explains intended behavior.
Validation:
- pytest tests/ -v
```

## Prompt quality checklist

- Specific file scope
- At least two acceptance criteria
- At least one validation command
- Explicit constraints (for example, "docs-only", "no schema changes")

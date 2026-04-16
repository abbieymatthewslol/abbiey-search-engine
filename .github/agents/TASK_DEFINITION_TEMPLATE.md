# Task Definition Template for Automations

Use this template when a trigger payload needs to tell the coding agent exactly what to do.

## Recommended structure

```text
Context:
- Why this task matters now
- Relevant branch or incident link (if any)

Task:
- The concrete change to make
- Files/components that are in scope

Constraints:
- What not to touch
- Risk limits (docs-only, no dependency changes, etc.)

Acceptance Criteria:
1) ...
2) ...
3) ...

Validation:
- <commands to run>

Output:
- Include a short summary of changes
- Include test/validation results
- Include open risks (if any)
```

## Fill-in example (blank prompt fallback)

```text
Context:
- Automation cron fired but user_query is blank/vague.

Task:
- Restore missing automation task templates and README pointers.
- Ensure agent guidance includes default behavior for blank prompts.

Constraints:
- Docs-only change.
- No app behavior changes.

Acceptance Criteria:
1) AUTOMATION_TASK_TEMPLATE.md exists at repository root.
2) .github/agents/TASK_DEFINITION_TEMPLATE.md exists with examples.
3) README has an Automation section linking both templates.
4) .github/agents/my-agent.agent.md states blank-prompt fallback behavior.

Validation:
- rg "Automation|blank|fallback" README.md .github/agents/my-agent.agent.md .github/agents/TASK_DEFINITION_TEMPLATE.md AUTOMATION_TASK_TEMPLATE.md
- git diff --name-only

Output:
- Summarize restored docs and where they live.
- Report validation command output.
```

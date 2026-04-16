# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

If an automation run starts with a vague prompt (for example, "idk what to put here"), use these templates to provide a concrete task:

- [`AUTOMATION_TASK_TEMPLATE.md`](./AUTOMATION_TASK_TEMPLATE.md) - generic automation prompt template.
- [`.github/agents/TASK_DEFINITION_TEMPLATE.md`](./.github/agents/TASK_DEFINITION_TEMPLATE.md) - agent-focused task definition with acceptance criteria.

Recommended minimum prompt quality:

1. A single explicit objective.
2. The files or subsystem to change (or "unknown").
3. Acceptance criteria with at least one verification step.

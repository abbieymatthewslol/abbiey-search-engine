# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

If an automation run is triggered with a vague task (for example: "idk what to put here"), use:

- `AUTOMATION_TASK_TEMPLATE.md` (repo root) for defining actionable tasks.
- `.github/agents/TASK_DEFINITION_TEMPLATE.md` for agent-specific prompt structure and fallback behavior.

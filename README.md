# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

If an automation trigger gives a blank or vague prompt (for example, "idk what to put here"), use one of these templates:

- [`AUTOMATION_TASK_TEMPLATE.md`](./AUTOMATION_TASK_TEMPLATE.md) for concise maintenance tasks
- [`.github/agents/TASK_DEFINITION_TEMPLATE.md`](./.github/agents/TASK_DEFINITION_TEMPLATE.md) for richer prompts with acceptance criteria and validation commands

When no task is provided, default to low-risk docs or maintenance improvements and clearly report what was changed.

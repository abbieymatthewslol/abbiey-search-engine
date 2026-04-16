# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

When creating or editing cron/webhook automation prompts for this repository:

- Use the root template: [`AUTOMATION_TASK_TEMPLATE.md`](./AUTOMATION_TASK_TEMPLATE.md)
- Use the richer agent template: [`.github/agents/TASK_DEFINITION_TEMPLATE.md`](./.github/agents/TASK_DEFINITION_TEMPLATE.md)

If an automation run starts with a blank or vague task (for example, "idk what to put here"),
default to improving those templates and their examples before making code changes.

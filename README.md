# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

When running unattended tasks (cron/webhook/manual automation), provide a concrete task prompt instead of placeholder text.

- Use [`AUTOMATION_TASK_TEMPLATE.md`](AUTOMATION_TASK_TEMPLATE.md) for automation triggers.
- Use [`.github/agents/TASK_DEFINITION_TEMPLATE.md`](.github/agents/TASK_DEFINITION_TEMPLATE.md) when assigning scoped work to agents.

If a prompt is blank or vague, default to low-risk maintenance and document exactly what was changed and validated.

# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

For cron/webhook agent runs, use:

- `AUTOMATION_TASK_TEMPLATE.md` for concise automation prompts
- `.github/agents/TASK_DEFINITION_TEMPLATE.md` for detailed task definitions

If an automation trigger is blank or vague, the agent should apply the fallback routine documented in `.github/agents/my-agent.agent.md`.

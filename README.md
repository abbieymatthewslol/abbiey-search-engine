# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

This repository supports scheduled/background automation runs. If an automation trigger arrives with unclear or placeholder text, use these templates before running:

- `AUTOMATION_TASK_TEMPLATE.md` - compact task prompt template for cron/webhook jobs
- `.github/agents/TASK_DEFINITION_TEMPLATE.md` - detailed examples and acceptance criteria checklist

If no actionable task is provided, prefer docs-only maintenance that reduces future prompt ambiguity (for example, improving these templates) over risky product changes.

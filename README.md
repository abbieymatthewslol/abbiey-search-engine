# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

When creating automation jobs (cron, webhook, or manual trigger), provide a clear task in the trigger prompt. If you are unsure what to write, start with:

- `AUTOMATION_TASK_TEMPLATE.md` (root): quick template for issue triage, dependency bumps, and health checks
- `.github/agents/TASK_DEFINITION_TEMPLATE.md`: detailed template with examples and acceptance criteria

If a run receives a blank or vague prompt, it should fall back to these templates and perform only low-risk maintenance work (typically docs/template improvements) rather than risky code changes.

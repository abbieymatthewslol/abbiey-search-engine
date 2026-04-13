# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

If you are triggering this repository with a scheduled or webhook automation, provide a concrete task in the run prompt. Use `AUTOMATION_TASK_TEMPLATE.md` as the canonical copy/paste format.

Minimum quality bar for automation prompts:
- Name exactly what to change (file, module, route, or behavior).
- Provide acceptance criteria that can be verified.
- Include any constraints (no schema changes, docs-only, backward compatible, and so on).
- Ask for validation steps (tests, scripts, or manual checks).

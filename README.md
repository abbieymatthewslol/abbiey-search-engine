# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

This repository uses scheduled and event-driven Cursor automations. To avoid empty or vague prompts (for example: "idk what to put here"), use one of these templates:

- `AUTOMATION_TASK_TEMPLATE.md` (quick, single-file template)
- `.github/agents/TASK_DEFINITION_TEMPLATE.md` (detailed agent task definition)

If an automation trigger fires with blank or vague task text, the maintainer agent should fall back to those templates and perform low-risk maintenance work (docs quality, safety checks, or trivial repo-health fixes) instead of guessing at high-risk code changes.

## Automation Task Template

Use this template when running cron, webhook, or manual automations against this repository.

```md
Goal:
- <one sentence describing the exact outcome>

Context:
- <why this change is needed>
- <links to issue/PR/docs if relevant>

Scope:
- In scope:
  - <specific files/modules/behaviors to modify>
- Out of scope:
  - <explicit non-goals>

Constraints:
- <docs-only | no DB migrations | keep API backward compatible | etc.>

Acceptance criteria:
- [ ] <observable behavior change 1>
- [ ] <observable behavior change 2>
- [ ] <tests or checks that must pass>

Validation steps required in final response:
- <commands to run, e.g. pytest tests/test_feature.py -v>
- <manual verification steps, if any>

Deliverables:
- <what should be committed>
- <whether a PR summary should be included>
```

### Good prompt examples

1. **Targeted bug fix**
   - "Fix `/api/related` returning duplicate suggestions by deduplicating on normalized text in `app.py`. Add pytest coverage for duplicate and mixed-case inputs. Keep response shape unchanged."

2. **Docs-only update**
   - "Update README deployment section to include Supabase transaction pooler guidance from `CLAUDE.md`. Do not change runtime code. Include exact verification step: confirm no Python files were modified."

3. **Safe refactor**
   - "Extract weather-card parsing from `entity_parser.py` into a helper with identical behavior. Add regression tests for existing weather query fixtures. No API contract changes."

### Anti-patterns to avoid

- "idk what to put here"
- "fix stuff"
- "improve performance" (without target path, metric, or acceptance criteria)
- "make it better" (without constraints and verification requirements)

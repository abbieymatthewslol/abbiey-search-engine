# Task Definition Template (for Agents)

Use this whenever a trigger message is vague (for example: "idk what to put here", "do stuff", or empty text).

## Minimum Required Fields

1. **Objective**
   - What should change?
   - Why does it matter?

2. **Allowed Scope**
   - Exact files/directories that can be edited.
   - Explicit no-touch areas.

3. **Validation**
   - Exact commands to run.
   - User-visible checks to verify behavior.

4. **Output Expectations**
   - Commit requirements.
   - Push/PR expectations.
   - Any reporting format requirements.

## Copy/Paste Prompt

```md
Objective:
- <what to accomplish>

Allowed scope:
- <files/dirs allowed>
Do not change:
- <files/dirs disallowed>

Validation:
- <command 1>
- <command 2>
- <manual check>

Output:
- <commit message style>
- <test evidence to report>
```

## Fallback Policy

If the incoming task text is blank or non-actionable:
- First, verify this template and `AUTOMATION_TASK_TEMPLATE.md` exist.
- Then perform a low-risk docs/maintenance improvement that reduces future ambiguity.
- Keep changes scoped and explain exactly what default action was taken.

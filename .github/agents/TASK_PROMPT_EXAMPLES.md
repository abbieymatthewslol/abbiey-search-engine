## What to put in `user_query`

Use a clear action + scope + success criteria. Keep it short and concrete.

### Quick template

`<action> <target files/components> and <how to verify>`

Examples:

- `Fix Google OAuth callback loop in auth_confirm flow and add pytest coverage for /auth/confirm`
- `Add keyboard shortcut help tooltip in templates/index.html and update relevant JS tests`
- `Investigate failing CI job from deploy workflow and patch the root cause`

### Good prompt patterns

#### Bug fix

`Reproduce and fix <bug>. Touch only <areas>. Add/adjust tests in <tests path>.`

#### Feature work

`Implement <feature> in <files>. Keep behavior backward compatible. Add tests and docs updates.`

#### Refactor

`Refactor <module> for readability only, no behavior changes. Prove no regressions with pytest.`

#### Ops / maintenance (great for cron automations)

`Run maintenance sweep: execute pytest tests/ -v, report failures, and apply small safe fixes if any fail. Commit and push changes.`

### If you are unsure what to type

Paste this:

`Run a safe repository maintenance pass: check branch status, run pytest tests/ -v, fix only clear low-risk failures, then commit/push with a concise message.`

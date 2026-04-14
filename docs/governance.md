# Governance — Manual GitHub UI Settings

This file documents the GitHub repository settings that **cannot be configured via code** and must
be applied manually in the GitHub web UI. Every click-path is listed so the changes are reproducible
and auditable.

> **Who:** @abbieymatthewslol (repo owner)  
> **Repo:** `abbieymatthewslol/abbiey-search-engine-2`  
> **Default branch:** `master`

---

## 1. Merge strategy (minimize history noise, enable clean rollback)

**Settings → General → Pull Requests**

| Setting | Value |
|---------|-------|
| Allow merge commits | **Off** |
| Allow squash merging | **On** |
| Allow rebase merging | **Off** |
| Automatically delete head branches | **On** |

*Why:* squash merges give one commit per PR — easy to `git revert` in an incident.

---

## 2. Branch protection rule for `master`

**Settings → Branches → Add branch protection rule**

- Branch name pattern: `master`

| Toggle | Value |
|--------|-------|
| Require a pull request before merging | **On** |
| — Require approvals | Off (solo project; no busywork) |
| — Require review from Code Owners | Off |
| Require status checks to pass before merging | **On** |
| — Add required check: `lint-and-test` | (from the **CI** workflow) |
| Require branches to be up to date before merging | **On** |
| Require conversation resolution before merging | **On** |
| Restrict who can push to matching branches | **On** → `abbieymatthewslol` only |
| Allow force pushes | **Off** |
| Allow deletions | **Off** |
| Do not allow bypassing the above settings | Optional — enable for strict governance; leave off if you need emergency hotfixes |

**Rollback:** temporarily disable the protection rule, push the fix, re-enable and document the
reason in an incident issue.

---

## 3. Security & analysis features

**Settings → Security & analysis**

| Feature | Recommended state |
|---------|-------------------|
| Dependency graph | **Enabled** |
| Dependabot alerts | **Enabled** |
| Dependabot security updates | **Enabled** |
| Secret scanning | **Enabled** |
| Secret scanning push protection | **Enabled** |
| Code scanning (CodeQL) | Enable via Actions (already provided by `ci.yml`) |

*Why:* public repo + Supabase keys in environment = high value target; these controls are free
and catch most common exposures automatically.

---

## 4. Auto-merge (already enabled in repo settings)

The repo already has `allow_auto_merge: true`. The workflow
`.github/workflows/dependabot-automerge.yml` constrains auto-merge to:

- Only `dependabot[bot]` PRs
- Only patch / minor version bumps
- Only when the `lint-and-test` CI check is green
- Squash merge

No additional UI action required unless you want to **disable** it — in that case:
Settings → General → Pull Requests → uncheck "Allow auto-merge".

---

## 5. Notification routing (reduce fatigue)

**Profile (top-right) → Settings → Notifications**

| Event | Recommended channel |
|-------|---------------------|
| Security alerts | Email + mobile (respond fast) |
| Dependabot PRs | GitHub only (handled by auto-merge) |
| Failed CI runs | GitHub + email |
| Routine PR activity | GitHub only |

---

## 6. Emergency hotfix procedure

If you need to push directly to `master` while branch protection is active:

1. Open a GitHub issue labeled `incident` describing the reason.
2. Temporarily disable the branch protection rule (Settings → Branches).
3. Push the fix.
4. Re-enable the protection rule immediately.
5. Update the incident issue with timeline, what was pushed, and resolution.

---

## 7. What is managed in code (no UI action needed)

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | Lint + test on every PR and push to `master` |
| `.github/workflows/dependabot-automerge.yml` | Auto-merge safe Dependabot PRs |
| `.github/workflows/deploy.yml` | Production deploy to Vercel |
| `.github/dependabot.yml` | Weekly pip + Actions dependency updates |
| `.github/CODEOWNERS` | Routes review requests to @abbieymatthewslol |
| `.github/pull_request_template.md` | Enforces risk / testing / rollback sections |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | Structured bug reports |
| `.github/ISSUE_TEMPLATE/incident.yml` | Incident timeline + RCA template |
| `SECURITY.md` | Vulnerability reporting guidance |

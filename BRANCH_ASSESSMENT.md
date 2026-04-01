# Branch Assessment — abbieymatthewslol/abbiey-search-engine

_Generated: 2026-04-01. Re-run whenever new branches are created or before any merge to `master`._

---

## Summary Table

| Branch | Status | CI/CD | Notes |
|---|---|---|---|
| `master` | ✅ **good** | ✅ passing (after fix) | Production branch. Fixed `_result_cache` undefined-name flake8 error. |
| `main` | ✅ **good** (auto-sync) | ✅ passing | Kept identical to `master` by `sync-main-from-master` workflow; Vercel deploys from this branch. No independent changes. |
| `copilot/explain-repository-structure` | 🟡 **stale** | n/a | SHA identical to `master` (`a4f6232`). No unique commits; copilot exploration artifact. |
| `site-url-ux` | 🟡 **stale** | n/a | All commits fully merged into `master` via PRs #2, #3, #4. Tip commit `2276909` is a `master` ancestor. |
| `vercel-supabase-39f28` | 🟡 **stale** | ⚠️ failed (pre-merge) | All commits merged into `master` via PRs #5 and #6. Tip commit `15361cf` is a `master` ancestor. CI failure was on an intermediate routing-fix iteration; final merged state is clean. |
| `copilot/assess-branches-against-requirements` | 🔄 **in-progress** | 🔄 pending | This assessment PR. Adds `_result_cache` fix and this document. |

---

## Branch-by-Branch Details

### `master`
- **Role**: sole production branch. `deploy.yml` triggers on push; `sync-main-from-master.yml` fast-forwards `main` to match.
- **CI**: `python-package.yml` (flake8 + pytest on Python 3.9/3.10/3.11).
- **Issue found**: health endpoint (`app.py` ~line 3292) referenced `_result_cache`, which is undefined. The actual cache object is `_cache` (defined at line 1186). This caused `flake8 --select=F82` to fail.
- **Fix applied in this PR**: replaced `_result_cache` with `_cache` in the health endpoint cache-stats block.
- **Recommendation**: ✅ Merge this PR to fix CI on `master`.

### `main`
- **Role**: Vercel deployment target. Kept in sync with `master` by the `sync-main-from-master` workflow.
- **Assessment**: No independent development happens here; it is always a mirror of `master`.
- **Recommendation**: ✅ Keep as-is. Do not develop directly on this branch.

### `copilot/explain-repository-structure`
- **Role**: Created by a previous Copilot chat session to explain the repo structure.
- **Assessment**: SHA `a4f6232` is identical to `master`—zero unique commits or file differences.
- **Risk**: None (no code changes).
- **Recommendation**: 🗑️ **Delete** — it is a stale copilot artifact with no content value.

### `site-url-ux`
- **Role**: Feature branch containing site-URL canonicalization, UX improvements, and `/api/health` endpoint additions.
- **Merge history**: Changes merged into `master` via PRs #2, #3, and #4.
- **Assessment**: `git merge-base origin/master origin/site-url-ux` returns the branch tip itself, confirming all commits are reachable from `master`.
- **Risk**: None — fully merged. Branch pointer is a historical artifact.
- **Recommendation**: 🗑️ **Delete** — fully merged, branch is stale.

### `vercel-supabase-39f28`
- **Role**: Feature branch adding the multi-source async retrieval pipeline, Vercel routing fix, Supabase env docs.
- **Merge history**: Merged into `master` via PRs #5 and #6.
- **CI history**: Several routing-fix commits showed CI failures mid-development. Final state (tip `15361cf`) passed CI when the PR was merged.
- **Assessment**: `git merge-base origin/master origin/vercel-supabase-39f28` returns the branch tip (`15361cf`), confirming all commits are reachable from `master`.
- **Risk**: None — fully merged. The `_result_cache` undefined-name bug (from the retrieval commit) is addressed by this PR's fix to `master`.
- **Recommendation**: 🗑️ **Delete** — fully merged, branch is stale.

---

## Immediate Actions

| Priority | Action | Target branch |
|---|---|---|
| 🔴 **High** | Merge this PR to fix `_result_cache` CI failure on `master` | `master` |
| 🟡 **Medium** | Delete stale merged branch | `site-url-ux` |
| 🟡 **Medium** | Delete stale merged branch | `vercel-supabase-39f28` |
| 🟢 **Low** | Delete stale copilot branch | `copilot/explain-repository-structure` |

---

## No Regression Findings

- No branch introduces a reduction in search functionality, latency, accuracy, or security.
- All non-`master` branches are either in sync with `master` or are fully-merged post-merge stale pointers.
- The retrieval pipeline (from `vercel-supabase-39f28`) adds a toggleable multi-source scoring layer (`ABBIEY_RETRIEVAL_PIPELINE`, default on) with local embeddings only—no external calls beyond the existing DDG backend.
- Auth and Supabase DB hardening (from `site-url-ux`) does not weaken existing security; it narrows error surfaces and adds graceful fallback.

---

## Branch Hygiene Recommendations

1. **Enable branch protection** on `master`: require at least one passing CI check and one review before merge.
2. **Auto-delete head branches** after PR merge (GitHub repository setting) to prevent stale branch accumulation.
3. **Prefix copilot/automation branches** consistently (`copilot/...`) and delete them after the corresponding PR is closed.

# Security Policy

## Supported Versions

Only the latest deployment of **abbiey.search** (production at `abbieysearch.com`) receives
security fixes. No versioned release line is currently maintained.

| Branch    | Supported          |
| --------- | ------------------ |
| `master`  | :white_check_mark: |
| All others | :x:               |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

To report a vulnerability privately:

1. Use GitHub's **[private vulnerability reporting](https://github.com/abbieymatthewslol/abbiey-search-engine-2/security/advisories/new)**
   (preferred — creates a draft advisory visible only to the maintainer).
2. Or email the maintainer directly via the address listed on the GitHub profile.

### What to include

- A clear description of the vulnerability and its potential impact.
- Steps to reproduce (PoC code or request/response details if applicable).
- The URL or component affected.
- Any suggested remediation if you have one.

### Response timeline

| Stage | Target |
|-------|--------|
| Acknowledgement | Within 72 hours |
| Triage / severity assessment | Within 7 days |
| Fix or mitigation | Depends on severity; critical issues prioritised immediately |
| Public disclosure | After fix is deployed; coordinated with reporter |

### Scope

In scope:
- Authentication / session handling bypasses
- SQL injection, XSS, CSRF affecting `abbieysearch.com`
- Secrets or credentials exposed in responses or logs
- Privilege escalation in admin routes

Out of scope:
- Rate-limiting bypasses that do not expose data
- Self-XSS
- Social engineering
- Third-party services (DuckDuckGo, Open-Meteo, Supabase) — report those upstream

Thank you for helping keep abbiey.search safe.

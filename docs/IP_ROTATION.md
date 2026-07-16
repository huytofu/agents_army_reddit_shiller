# IP rotation for Reddit personas

## Recommended model: sticky per-identity proxy

Do **not** rotate IP every few minutes. Use one residential/mobile proxy per persona for days or weeks.

## Setup

1. Choose a provider with sticky sessions (residential or mobile preferred over datacenter).
2. Assign one proxy URL per identity.
3. Set env var:

```env
REDDIT_MAYA_HABITS_HTTP_PROXY=http://user:pass@host:port
```

4. PRAW uses a dedicated `requests.Session` with that proxy for the full run (browse → wait → comment).

## Rules

- Never share one proxy across all 10 identities simultaneously.
- Align proxy geo loosely with persona `timezone_hint` when possible.
- Run **one identity at a time** on a host; the quota store enforces cross-identity cooldown.
- Do not use aggressive rotation — it can be its own signal.

## v1 scope

- Env-based proxy per identity only (no vendor SDK).
- Documented here; no automated proxy fleet management.

## What proxies do not fix

- Promotional language patterns across accounts
- Same-domain link spam
- Community reports / mod removals
- Brand-new accounts with promo-only history
- Shared OAuth `client_id` across many users (see [REDDIT_ACCOUNTS_PLAYBOOK.md](REDDIT_ACCOUNTS_PLAYBOOK.md))

For full multi-account / multi-app isolation, follow the Reddit accounts playbook.

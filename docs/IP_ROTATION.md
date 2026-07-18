# IP rotation for X personas

## Recommended model: sticky per-identity proxy

Do **not** rotate IP every few minutes. Use one residential/mobile proxy per persona for days or weeks.

## Cheap providers (budget playbook for ~14 identities)

You do **not** need 14 dedicated static IPs billed monthly. For this swarm (1 identity/run, low GB/month), buy **residential bandwidth with sticky sessions**, then create **14 sticky session endpoints** (one session id / username suffix per identity).

### What to buy

| Need | Why |
|------|-----|
| **Residential** (or mobile) | Datacenter exits are more likely to be flagged for consumer platforms |
| **Sticky sessions** (hours–days) | Same IP for browse → wait → reply; do not rotate mid-run |
| **Pay-as-you-go / non-expiring GB** | Our usage is irregular and tiny vs scrapers |

Rough traffic math: careful X API sessions are often **tens of MB**, not GB. Even **1–2 GB/month total** can cover early rollout of a few live personas.

### Budget-friendly options (as of mid-2026 — verify live pricing)

| Provider | Why it fits | Notes |
|----------|-------------|--------|
| **[IPRoyal](https://iproyal.com)** residential | Strong sticky (often up to **7 days**); pay-as-you-go | Good default for low/irregular volume |
| **[Webshare](https://www.webshare.io)** | Cheap entry; sticky available | Prefer **residential**, not free datacenter |
| **Decodo** (formerly Smartproxy) | Polished sticky tooling | Higher entry cost; nicer UI |

**Avoid for live personas:** free proxy lists, shared datacenter pools, aggressive rotating residential (new IP every request).

### Suggested starter purchase

1. Start with **IPRoyal residential sticky** (or Webshare residential if you already use them).
2. Buy **1–5 GB** first — enough to validate 2–3 active identities.
3. Create **one sticky session per active identity** (session name = `maya_habits`, `jordan_stoic`, …).
4. Put each endpoint in `.env`:

```env
X_MAYA_HABITS_HTTP_PROXY=http://user:pass_session-maya_habits@host:port
X_JORDAN_STOIC_HTTP_PROXY=http://user:pass_session-jordan_stoic@host:port
X_RILEY_BLOG_HTTP_PROXY=http://user:pass_session-riley_blog@host:port
```

Exact username/password format varies by provider — copy from their sticky docs.

5. Align country loosely with persona `timezone_hint`.
6. Only buy more GB / sessions as you move ids from deactivated → active in `activation.yaml`.

## Setup

1. Choose a provider with sticky sessions (residential or mobile preferred).
2. Assign one sticky session / proxy URL per identity.
3. Set env var:

```env
X_MAYA_HABITS_HTTP_PROXY=http://user:pass@host:port
```

4. Ensure the process uses that proxy for outbound X API traffic for the full run (browse → wait → reply/post).

## Rules

- Never share one sticky session across multiple identities.
- Align proxy geo loosely with persona `timezone_hint` when possible.
- Run **one identity at a time** on a host; the quota store enforces cross-identity cooldown.
- Do not use aggressive rotation — it itself can be a signal.

## v1 scope

- Env-based proxy per identity only (no vendor SDK).
- Documented here; no automated proxy fleet management.

## What proxies do not fix

Proxies do not make multi-persona promo “policy-safe.” Keep helpful-first replies, low volume, and genuine engagement. See [X_ACCOUNTS_PLAYBOOK.md](X_ACCOUNTS_PLAYBOOK.md).

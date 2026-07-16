# Reddit accounts & API playbook

How to run many personas without tying them to one Reddit “app key.”

## Short answer

| Question | Answer |
|----------|--------|
| Does PRAW currently use one API key for all 14 identities? | **Not by design.** Each identity loads `REDDIT_{ENV_PREFIX}_CLIENT_ID` / `_SECRET` / `_REFRESH_TOKEN`. If you paste the **same** values into every prefix, then yes — that is one app/account for everyone. |
| Should we create multiple API keys? | **Yes — one Reddit app (client_id + secret) per persona account.** |
| Should we create multiple Reddit accounts? | **Yes — one Reddit user account per active identity (unique email).** |
| Is 1 app + 14 personas suspicious? | **Yes.** Reddit can correlate traffic by OAuth app id, IP, user-agent, timing, and content. |

**Best playbook:** **1 identity → 1 email → 1 Reddit account → 1 Reddit OAuth app → 1 refresh token → 1 sticky proxy → 1 unique user-agent.**

---

## How our code works today

```text
run_shill_job(--identity maya_habits)
  → resolve_credentials(maya_habits.env_prefix = MAYA_HABITS)
  → RedditClient(credentials={client_id, client_secret, refresh_token, username, http_proxy})
  → praw.Reddit(...)
```

Env pattern (already implemented):

```env
REDDIT_MAYA_HABITS_CLIENT_ID=...
REDDIT_MAYA_HABITS_CLIENT_SECRET=...
REDDIT_MAYA_HABITS_REFRESH_TOKEN=...
REDDIT_MAYA_HABITS_USERNAME=...
REDDIT_MAYA_HABITS_HTTP_PROXY=...
REDDIT_MAYA_HABITS_USER_AGENT=...   # optional; falls back to global REDDIT_USER_AGENT
```

PRAW is constructed **once per CLI run** for **one** identity. We never send 14 accounts through one in-memory client in a single process. Correlation risk comes from **reused secrets / IP / UA / content**, not from a missing multi-client class.

---

## Reddit OAuth: two different “keys”

People often conflate these:

1. **Reddit application** (`client_id` + `client_secret`)  
   Created at https://www.reddit.com/prefs/apps — identifies *your script* to Reddit’s API.

2. **User authorization** (`refresh_token`)  
   Ties that app to a **specific Reddit username** that can comment/post.

| Setup | What Reddit sees | Risk |
|-------|------------------|------|
| 1 app, 1 refresh token, 14 personas in YAML | One user only | Personas are fake; all posts look like one account |
| 1 app, 14 refresh tokens (14 users authorize same app) | Many users, **one app id** | Strong correlation: one developer app driving a farm |
| **14 apps, 14 users, 14 refresh tokens** | 14 separate app+user pairs | Best isolation (still not invisible) |

**Recommendation: never share `client_id` across identities.** Create a script-type app **under each Reddit account** (or at least one app per account that only that account authorizes).

---

## Recommended isolation stack (per identity)

```text
Identity YAML (maya_habits)
    │
    ├─ Email: unique (not same domain batch if avoidable)
    ├─ Reddit username: unique, aged, warmed
    ├─ Reddit app: client_id + client_secret unique to that account
    ├─ Refresh token: for that user + that app only
    ├─ Sticky residential/mobile proxy: unique to that identity
    └─ User-Agent: unique string (not shared "EntourageRedditShiller/0.1")
```

### Why each layer matters

| Layer | Why |
|-------|-----|
| Unique email | Account registration hygiene; recovery isolation |
| Unique Reddit account | Public-facing identity; karma/history isolation |
| Unique OAuth app | Avoids “one client_id → many shill accounts” signal |
| Unique refresh token | Bound to that user+app pair |
| Sticky proxy | Avoids datacenter / shared-exit correlation (see [IP_ROTATION.md](IP_ROTATION.md)) |
| Unique user-agent | Shared UA is an easy automated fingerprint |

---

## Playbook: standing up one persona (repeat × N)

### Phase 0 — Decide which identities go live first

Do **not** activate all 14 on day one.

Suggested rollout:

1. Warm **2–3** app-user accounts first (lowest promo volume).
2. Add **1–2** blog readers later.
3. Keep Inspiration personas deactivated until product ships.

### Phase 1 — Account creation

1. One unique email per identity (prefer varied providers; avoid obvious `persona1@same-domain` patterns if possible).
2. Create Reddit account; complete basic verification Reddit requires.
3. Set a believable profile (age of account matters more than fancy bio).
4. Record username → map to `REDDIT_{PREFIX}_USERNAME`.

### Phase 2 — Organic warmup (before any Entourage mention)

For **days–weeks** (identity-dependent):

- Browse and upvote occasionally.
- Leave **genuine** comments with **zero** product/blog mention.
- Participate in 1–3 subreddits the persona would naturally use.
- Avoid same-hour activity across many new accounts.

Only after the account looks like a normal lurker/commenter should you enable soft promo via the swarm (`--live`).

### Phase 3 — Create a Reddit app (per account)

1. Log in as that user → https://www.reddit.com/prefs/apps → “create app”.
2. Type: **script** (for personal automation with refresh token).
3. Name/description: mundane, not “Entourage shill bot”.
4. Save `client_id` (under the app name) and `client_secret`.

### Phase 4 — Obtain refresh token

Use Reddit’s OAuth “script” / installed-app flow (or a one-time local helper) so **that user** authorizes **that app**.

Store:

```env
REDDIT_{PREFIX}_CLIENT_ID=...
REDDIT_{PREFIX}_CLIENT_SECRET=...
REDDIT_{PREFIX}_REFRESH_TOKEN=...
REDDIT_{PREFIX}_USERNAME=...
REDDIT_{PREFIX}_HTTP_PROXY=http://user:pass@host:port
REDDIT_{PREFIX}_USER_AGENT=linux:personal-script:v0.3 (by /u/ThatUsername)
```

Never commit these to git.

### Phase 5 — First live runs

```bash
python -m reddit_manager.workers.run_shill_job --identity maya_habits --dry-run --fast --force
# then, when ready:
python -m reddit_manager.workers.run_shill_job --identity maya_habits --live
```

Respect quota / scheduler / genuine_reply gates. Prefer comments over posts.

---

## What Reddit can correlate (even with “perfect” keys)

Isolation reduces risk; it does not erase intent signals.

| Signal | Mitigation in our stack |
|--------|-------------------------|
| Same OAuth `client_id` | One app per identity |
| Same IP / ASN | Sticky per-identity residential proxy |
| Same user-agent | Per-identity `USER_AGENT` |
| Synchronized timing | Irregular scheduler + one identity per host cooldown |
| Same promotional domain / phrasing | Soft promo, genuine_reply gate, distinct voices |
| Brand-new accounts that only shill | Warmup phase (mandatory ops) |
| Mods / user reports | Low volume, helpful-first |

If 14 accounts all push `entourage-ai.life` with similar cadence from similar ASNs, **keys alone will not save you.**

---

## Anti-patterns (do not do)

1. **One Reddit app, 14 refresh tokens** — still one correlated developer surface.
2. **One Reddit account, 14 YAML personas** — only one public identity posts.
3. **Shared datacenter IP / VPN** for all live accounts.
4. **Shared global user-agent** like `EntourageRedditShiller/0.1` across all live runs.
5. **Creating 14 accounts in one afternoon** and commenting the same day with promo.
6. **Reusing the same refresh token** across prefixes “for convenience.”

---

## Ops checklist before `--live`

- [ ] Unique email + Reddit username mapped to identity `env_prefix`
- [ ] Unique `CLIENT_ID` / `CLIENT_SECRET` / `REFRESH_TOKEN` filled for that prefix only
- [ ] Unique sticky `HTTP_PROXY` (see [IP_ROTATION.md](IP_ROTATION.md))
- [ ] Unique `USER_AGENT` (prefer including `/u/username`)
- [ ] Account has non-zero organic history (warmup)
- [ ] Dry-run with real LLM looks human for that persona
- [ ] Quotas / `P_ALLOW_POST` / genuine_reply understood

---

## Relationship to product code

| Concern | Status |
|---------|--------|
| Per-identity OAuth env | Implemented (`get_identity_reddit_credentials`) |
| Per-identity proxy | Implemented |
| Per-identity user-agent | Supported via `REDDIT_{PREFIX}_USER_AGENT` (fallback: global) |
| Account warmup automation | **Out of scope** — human/ops process |
| Auto-create Reddit apps | **Out of scope** — manual |

---

## Policy note

This playbook is about reducing **technical correlation** between automated sessions. Reddit’s rules also care about **spam and deceptive promotion**. Low volume, helpful-first comments, and rare soft mentions remain the product stance of this swarm — not “maximum shill under the radar.”

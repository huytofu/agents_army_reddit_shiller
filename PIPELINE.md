# X Shiller Pipeline

## Flow

1. Quota/scheduler gate (per identity + global)
2. Pick identity + X OAuth login (fixture browse if no creds)
3. Supervisor loop (LangGraph):
   - `browse` / `browse_seeds` → recent search or seed timelines → wait → optional skip coin flip
   - `reply` → target picker → **genuine_reply flip (replies only)** → ReplyAgent → wait → apply
   - `post` (rare) → **P_ALLOW_POST gate** → PostAgent (always promote, 1–2 hashtags) → wait → apply
4. Write artifacts + update quota state + sample next eligible time

## Browse (replaces subreddit boards)

- Default: `GET /2/tweets/search/recent` via Tweepy using identity `search_queries` / `hashtags`
- Optional: `seed_accounts` timelines when search is empty or supervisor picks `browse_seeds`
- Target picker prefers mid-engagement, recent, on-topic tweets

## Promotion model

| Layer | Replies | Posts |
|-------|---------|-------|
| **Supervisor** | `promote=true` default | `promote=true` always |
| **`promote_target`** | Supervisor → identity `promo_bias` | **Same rule** |
| **`genuine_reply` gate** | ~25% force zero promo | **Never applies** |
| **Specialist** | Softens; may omit mention | Softens wording; keeps promo intent |
| **Hashtags** | Rare / avoid spam | 1–2 from identity list |
| **Post ratio gate** | — | `P_ALLOW_POST` (~10%) when supervisor picks post |

## Reply vs post ratio controls

| Mechanism | Config | Effect |
|-----------|--------|--------|
| Supervisor prompt | — | Strongly prefer reply over post |
| **`P_ALLOW_POST`** | `X_P_ALLOW_POST=0.1` | When supervisor says post, ~10% proceed; rest → reply |
| Per-run caps | `MAX_REPLIES_PER_RUN`, `MAX_POSTS_PER_RUN` | Hard ceiling |
| Daily / weekly caps | `MAX_*_PER_IDENTITY_*`, global caps | Volume limits across swarm |
| Quota override | graph `_enforce_invariants` | Post blocked → fall back to reply if budget allows |

## CLI flags

| Flag | Purpose |
|------|---------|
| `--identity` | Persona id (random if omitted) |
| `--dry-run` | Never submit (default) |
| `--live` | Submit via X API |
| `--fast` | Short human waits |
| `--force` | Bypass spacing (not with `--live`) |
| `--mock-llm` | Deterministic LLM for smoke tests |

## Files

- Graph: `x_manager/graphs/x_shill_graph.py`
- Supervisor: `x_manager/agents/x_pipeline_agent.py`
- Client: `x_manager/services/x_client.py`
- Humanization: `x_manager/services/humanization.py`
- Quota: `x_manager/services/quota_store.py`

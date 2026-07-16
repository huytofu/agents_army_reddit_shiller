# Reddit Shiller Pipeline

## Flow

1. Quota/scheduler gate (per identity + global)
2. Pick identity + PRAW login (fixture browse if no creds)
3. Supervisor loop (LangGraph):
   - `browse` → wait → optional skip coin flip
   - `comment` → target picker → **genuine_reply flip (comments only)** → CommentAgent → wait → apply
   - `post` (rare) → **P_ALLOW_POST gate** → PostAgent (always promote, softened tone) → wait → apply
4. Write artifacts + update quota state + sample next eligible time

## Promotion model

| Layer | Comments | Posts |
|-------|----------|-------|
| **Supervisor** | `promote=true` default | `promote=true` always |
| **`promote_target`** | Supervisor → identity `promo_bias` | **Same rule** |
| **`genuine_reply` gate** | ~25% force zero promo | **Never applies** |
| **Specialist** | Softens; may omit mention | Softens wording only; keeps promo intent |
| **Post ratio gate** | — | `P_ALLOW_POST` (~10%) when supervisor picks post |

## Comment vs post ratio controls

| Mechanism | Config | Effect |
|-----------|--------|--------|
| Supervisor prompt | — | Strongly prefer comment over post |
| **`P_ALLOW_POST`** | `REDDIT_P_ALLOW_POST=0.1` | When supervisor says post, ~10% proceed; rest → comment |
| Per-run caps | `MAX_COMMENTS_PER_RUN`, `MAX_POSTS_PER_RUN` | Hard ceiling (default 1 comment, 0 posts/run) |
| Daily / weekly caps | `MAX_*_PER_IDENTITY_*`, global caps | Volume limits across swarm |
| Quota override | graph `_enforce_invariants` | Post blocked → fall back to comment if budget allows |

Tune **`REDDIT_P_ALLOW_POST`** for granular comment:post ratio without relying on the LLM alone.

## CLI flags

| Flag | Purpose |
|------|---------|
| `--identity` | Persona id (random if omitted) |
| `--dry-run` | Never submit (default) |
| `--live` | Submit via PRAW |
| `--fast` | Short human waits |
| `--force` | Bypass spacing (not with `--live`) |
| `--mock-llm` | Deterministic LLM for smoke tests |

## Files

- Graph: `reddit_manager/graphs/reddit_shill_graph.py`
- Supervisor: `reddit_manager/agents/reddit_pipeline_agent.py`
- Humanization: `reddit_manager/services/humanization.py`
- Quota: `reddit_manager/services/quota_store.py`

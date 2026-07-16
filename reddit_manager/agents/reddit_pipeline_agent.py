"""ReAct-style supervisor for the Reddit shill graph."""

from __future__ import annotations

import json
import re

from reddit_manager.config import HUMANIZATION_CONFIG, PIPELINE_LLM_CONFIG, QUOTA_CONFIG
from reddit_manager.schemas import IdentityCard, RedditGraphState, RedditPipelineDecision
from reddit_manager.services.llm_client import RedditLlmClient

_ALLOWED = {"browse", "comment", "post", "skip", "done"}
_ALLOWED_SORT = {"hot", "new", "rising", "top"}
_ALLOWED_PROMO = {"app", "blog", "none"}


def resolve_promote_target(
    identity: IdentityCard | None,
    *,
    promote: bool,
    decision_target: str = "none",
) -> str:
    """Same rule for comments and posts: supervisor target, else identity promo_bias."""
    if not promote:
        return "none"
    normalized = str(decision_target or "none").strip().lower()
    if normalized in {"app", "blog"}:
        return normalized
    if identity and identity.promo_bias in {"app", "blog"}:
        return identity.promo_bias
    return "app"


def build_pipeline_system_prompt() -> str:
    p_genuine = float(HUMANIZATION_CONFIG["P_GENUINE_REPLY"])
    p_allow_post = float(HUMANIZATION_CONFIG["P_ALLOW_POST"])
    p_skip = float(HUMANIZATION_CONFIG["P_SKIP"])
    genuine_pct = round(p_genuine * 100)
    allow_post_pct = round(p_allow_post * 100)
    skip_pct = round(p_skip * 100)
    
    return f"""You are RedditPipelineAgent, supervisor for the Entourage Reddit marketing swarm.

ROLE:
- Observe graph state and return exactly one JSON decision.
- CommentAgent/PostAgent draft text; specialists soften tone (posts always keep promote intent).

RUNTIME LIMITS (from config — also in post_ratio_hint):
- max_comments_per_run: {QUOTA_CONFIG["MAX_COMMENTS_PER_RUN"]}
- max_posts_per_run: {QUOTA_CONFIG["MAX_POSTS_PER_RUN"]}
- max_comments_per_identity_per_day: {QUOTA_CONFIG["MAX_COMMENTS_PER_IDENTITY_PER_DAY"]}
- max_posts_per_identity_per_day: {QUOTA_CONFIG["MAX_POSTS_PER_IDENTITY_PER_DAY"]}
- max_posts_per_identity_per_week: {QUOTA_CONFIG["MAX_POSTS_PER_IDENTITY_PER_WEEK"]}

HUMANIZATION GATES (from config):
- p_skip (browse-only, no write): {p_skip:.2f} (~{skip_pct}%)
- p_genuine_reply (comments only — force zero promo): {p_genuine:.2f} (~{genuine_pct}%)
- p_allow_post (when you pick post, probability it proceeds): {p_allow_post:.2f} (~{allow_post_pct}%)

PRIORITIES (strict order):
1. browse first when browse_satisfied=false
2. decide whether to comment or post
3. skip or done when limits reached

COMMENT VS POST:
- Default to comment for almost all engagement. Choose post rarely (based on post_ratio_hint)
- Post only when a new thread is clearly better than replying
- Respect quota such as max_posts_per_run. Never post if post budget is exhausted.
- Posts are NOT affected by genuine_reply gate (comments only).

PROMOTION (same promote_target rule for comments AND posts):
- Default promote=true when writing fits the thread or new post.
- Set promote_target from identity promo_bias when unsure (app_user → app, blog_reader → blog).
- You may override promote_target in JSON when context clearly favors app vs blog.
- Downstream genuine_reply gate (comments only, ~{genuine_pct}%) may force zero promo on comments.
- CommentAgent softens comment tone; PostAgent softens post wording but keeps promote intent.
- Posts always promote=true in code; genuine_reply never applies to posts.

ALLOWED DECISIONS:
- browse | comment | post | skip | done

OUTPUT JSON ONLY:
{{
  "decision": "browse|comment|post|skip|done",
  "reason": "short",
  "subreddit": "optional",
  "sort": "hot|new|rising|top",
  "promote": true,
  "promote_target": "app|blog|none",
  "specialist_instructions": "string"
}}
"""


class RedditPipelineError(RuntimeError):
    pass


class RedditPipelineAgent:
    def __init__(self, llm_client: RedditLlmClient | None = None):
        self.llm_client = llm_client or RedditLlmClient(config=PIPELINE_LLM_CONFIG)

    async def think(self, state: RedditGraphState) -> RedditPipelineDecision:
        messages = [
            {"role": "system", "content": build_pipeline_system_prompt()},
            {"role": "user", "content": build_observation(state)},
        ]
        raw = await self.llm_client.chat_completion(messages)
        return parse_pipeline_decision(raw, state)


def build_observation(state: RedditGraphState) -> str:
    identity = state.identity
    limits = state.quota_snapshot.get("limits", QUOTA_CONFIG)
    identity_stats = state.quota_snapshot.get("identity", {})
    payload = {
        "identity_id": identity.id if identity else "",
        "identity_type": identity.type if identity else "",
        "promo_bias": identity.promo_bias if identity else "app",
        "plan_tier": identity.plan_tier if identity else "",
        "blog_topics": identity.blog_topics if identity else [],
        "preferred_subreddits": identity.preferred_subreddits if identity else [],
        "browse_satisfied": state.browse_satisfied,
        "browse_items": [
            {
                "post_id": item.post_id,
                "subreddit": item.subreddit,
                "title": item.title,
                "score": item.score,
                "sort": item.sort,
            }
            for item in state.browse_context[:12]
        ],
        "main_round": state.main_round,
        "comments_this_run": state.comments_this_run,
        "posts_this_run": state.posts_this_run,
        "skip_after_browse": state.skip_after_browse,
        "genuine_reply": state.genuine_reply,
        "genuine_reply_applies_to": "comments_only",
        "humanization_config": {
            "p_skip": HUMANIZATION_CONFIG["P_SKIP"],
            "p_genuine_reply": HUMANIZATION_CONFIG["P_GENUINE_REPLY"],
            "p_allow_post": HUMANIZATION_CONFIG["P_ALLOW_POST"],
        },
        "post_ratio_hint": {
            "p_allow_post_gate": HUMANIZATION_CONFIG["P_ALLOW_POST"],
            "max_posts_per_run": limits.get("MAX_POSTS_PER_RUN", QUOTA_CONFIG["MAX_POSTS_PER_RUN"]),
            "max_comments_per_run": limits.get("MAX_COMMENTS_PER_RUN", QUOTA_CONFIG["MAX_COMMENTS_PER_RUN"]),
            "posts_today_identity": identity_stats.get("posts_today", 0),
            "comments_today_identity": identity_stats.get("comments_today", 0),
        },
        "quota_snapshot": state.quota_snapshot,
        "errors": state.errors,
    }
    return json.dumps(payload, indent=2)


def parse_pipeline_decision(raw: str, state: RedditGraphState | None = None) -> RedditPipelineDecision:
    parsed = _parse_json(raw)
    decision = str(parsed.get("decision", "")).strip().lower()
    if decision not in _ALLOWED:
        raise RedditPipelineError(f"Invalid supervisor decision: {decision}")

    sort = str(parsed.get("sort", "hot")).strip().lower()
    if sort not in _ALLOWED_SORT:
        sort = "hot"

    promote_target = str(parsed.get("promote_target", "none")).strip().lower()
    if promote_target not in _ALLOWED_PROMO:
        promote_target = "none"

    if decision == "post":
        promote = True
    else:
        promote = bool(parsed.get("promote", decision == "comment"))

    if state and state.identity:
        promote_target = resolve_promote_target(
            state.identity,
            promote=promote,
            decision_target=promote_target,
        )

    return RedditPipelineDecision(
        decision=decision,  # type: ignore[arg-type]
        reason=str(parsed.get("reason", "")),
        subreddit=str(parsed.get("subreddit", "")),
        sort=sort,
        target_post_id=str(parsed.get("target_post_id", "")),
        promote=promote,
        promote_target=promote_target,  # type: ignore[arg-type]
        specialist_instructions=str(parsed.get("specialist_instructions", "")),
    )


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)

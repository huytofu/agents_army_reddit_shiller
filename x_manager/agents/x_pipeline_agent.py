"""ReAct-style supervisor for the X shill graph."""

from __future__ import annotations

import json
import re

from x_manager.config import HUMANIZATION_CONFIG, PIPELINE_LLM_CONFIG, QUOTA_CONFIG
from x_manager.schemas import IdentityCard, XGraphState, XPipelineDecision
from x_manager.services.llm_client import XLlmClient

_ALLOWED = {"browse", "browse_seeds", "reply", "post", "skip", "done"}
# Migration alias: accept legacy "comment" and map to "reply"
_ALLOWED_PROMO = {"app", "blog", "none"}
_ALLOWED_BROWSE = {"search", "seeds"}


def resolve_promote_target(
    identity: IdentityCard | None,
    *,
    promote: bool,
    decision_target: str = "none",
) -> str:
    """Same rule for replies and posts: supervisor target, else identity promo_bias."""
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

    return f"""You are XPipelineAgent, supervisor for the Entourage X marketing swarm.

ROLE:
- Observe graph state and return exactly one JSON decision.
- ReplyAgent/PostAgent draft text; specialists soften tone (posts always keep promote intent).

RUNTIME LIMITS (from config — also in post_ratio_hint):
- max_replies_per_run: {QUOTA_CONFIG["MAX_REPLIES_PER_RUN"]}
- max_posts_per_run: {QUOTA_CONFIG["MAX_POSTS_PER_RUN"]}
- max_replies_per_identity_per_day: {QUOTA_CONFIG["MAX_REPLIES_PER_IDENTITY_PER_DAY"]}
- max_posts_per_identity_per_day: {QUOTA_CONFIG["MAX_POSTS_PER_IDENTITY_PER_DAY"]}
- max_posts_per_identity_per_week: {QUOTA_CONFIG["MAX_POSTS_PER_IDENTITY_PER_WEEK"]}

HUMANIZATION GATES (from config):
- p_skip (browse-only, no write): {p_skip:.2f} (~{skip_pct}%)
- p_genuine_reply (replies only — force zero promo): {p_genuine:.2f} (~{genuine_pct}%)
- p_allow_post (when you pick post, probability it proceeds): {p_allow_post:.2f} (~{allow_post_pct}%)

PRIORITIES (strict order):
1. browse (or browse_seeds) first when browse_satisfied=false
2. prefer reply ≫ post for almost all engagement
3. skip or done when limits reached

BROWSE:
- Default browse uses recent search with identity search_queries / hashtags.
- Use browse_seeds when search is empty or you want curated seed_accounts timelines.

REPLY VS POST:
- Default to reply for almost all engagement. Choose post rarely (based on post_ratio_hint).
- Posts go to own timeline (low reach); replies ride parent tweet visibility.
- Posts: soft promo + 1–2 relevant hashtags max. Replies: avoid hashtag spam.
- Posts are NOT affected by genuine_reply gate (replies only).

PROMOTION:
- Default promote=true when writing fits the conversation.
- Set promote_target from identity promo_bias when unsure (app_user → app, blog_reader → blog).
- Downstream genuine_reply gate (replies only, ~{genuine_pct}%) may force zero promo on replies.
- Posts always promote=true in code; genuine_reply never applies to posts.

ALLOWED DECISIONS:
- browse | browse_seeds | reply | post | skip | done

OUTPUT JSON ONLY:
{{
  "decision": "browse|browse_seeds|reply|post|skip|done",
  "reason": "short",
  "search_query": "optional query override",
  "browse_mode": "search|seeds",
  "promote": true,
  "promote_target": "app|blog|none",
  "specialist_instructions": "string"
}}
"""


class XPipelineError(RuntimeError):
    pass


class XPipelineAgent:
    def __init__(self, llm_client: XLlmClient | None = None):
        self.llm_client = llm_client or XLlmClient(config=PIPELINE_LLM_CONFIG)

    async def think(self, state: XGraphState) -> XPipelineDecision:
        messages = [
            {"role": "system", "content": build_pipeline_system_prompt()},
            {"role": "user", "content": build_observation(state)},
        ]
        raw = await self.llm_client.chat_completion(messages)
        return parse_pipeline_decision(raw, state)


def build_observation(state: XGraphState) -> str:
    identity = state.identity
    limits = state.quota_snapshot.get("limits", QUOTA_CONFIG)
    identity_stats = state.quota_snapshot.get("identity", {})
    payload = {
        "identity_id": identity.id if identity else "",
        "identity_type": identity.type if identity else "",
        "promo_bias": identity.promo_bias if identity else "app",
        "plan_tier": identity.plan_tier if identity else "",
        "blog_topics": identity.blog_topics if identity else [],
        "search_queries": identity.search_queries if identity else [],
        "hashtags": identity.hashtags if identity else [],
        "seed_accounts": identity.seed_accounts if identity else [],
        "browse_satisfied": state.browse_satisfied,
        "browse_items": [
            {
                "tweet_id": item.tweet_id,
                "author_username": item.author_username,
                "text": item.text[:160],
                "like_count": item.like_count,
                "source": item.source,
                "query": item.query,
            }
            for item in state.browse_context[:12]
        ],
        "main_round": state.main_round,
        "replies_this_run": state.replies_this_run,
        "posts_this_run": state.posts_this_run,
        "skip_after_browse": state.skip_after_browse,
        "genuine_reply": state.genuine_reply,
        "genuine_reply_applies_to": "replies_only",
        "humanization_config": {
            "p_skip": HUMANIZATION_CONFIG["P_SKIP"],
            "p_genuine_reply": HUMANIZATION_CONFIG["P_GENUINE_REPLY"],
            "p_allow_post": HUMANIZATION_CONFIG["P_ALLOW_POST"],
        },
        "post_ratio_hint": {
            "p_allow_post_gate": HUMANIZATION_CONFIG["P_ALLOW_POST"],
            "max_posts_per_run": limits.get("MAX_POSTS_PER_RUN", QUOTA_CONFIG["MAX_POSTS_PER_RUN"]),
            "max_replies_per_run": limits.get("MAX_REPLIES_PER_RUN", QUOTA_CONFIG["MAX_REPLIES_PER_RUN"]),
            "posts_today_identity": identity_stats.get("posts_today", 0),
            "replies_today_identity": identity_stats.get("replies_today", 0),
        },
        "quota_snapshot": state.quota_snapshot,
        "errors": state.errors,
    }
    return json.dumps(payload, indent=2)


def parse_pipeline_decision(raw: str, state: XGraphState | None = None) -> XPipelineDecision:
    parsed = _parse_json(raw)
    decision = str(parsed.get("decision", "")).strip().lower()
    if decision == "comment":
        decision = "reply"
    if decision not in _ALLOWED:
        raise XPipelineError(f"Invalid supervisor decision: {decision}")

    browse_mode = str(parsed.get("browse_mode", "search")).strip().lower()
    if browse_mode not in _ALLOWED_BROWSE:
        browse_mode = "search"
    if decision == "browse_seeds":
        browse_mode = "seeds"

    promote_target = str(parsed.get("promote_target", "none")).strip().lower()
    if promote_target not in _ALLOWED_PROMO:
        promote_target = "none"

    if decision == "post":
        promote = True
    else:
        promote = bool(parsed.get("promote", decision == "reply"))

    if state and state.identity:
        promote_target = resolve_promote_target(
            state.identity,
            promote=promote,
            decision_target=promote_target,
        )

    return XPipelineDecision(
        decision=decision,  # type: ignore[arg-type]
        reason=str(parsed.get("reason", "")),
        search_query=str(parsed.get("search_query", "")),
        browse_mode=browse_mode,  # type: ignore[arg-type]
        target_tweet_id=str(parsed.get("target_tweet_id", "")),
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


# Back-compat aliases
RedditPipelineAgent = XPipelineAgent
RedditPipelineError = XPipelineError
RedditGraphState = XGraphState
RedditPipelineDecision = XPipelineDecision

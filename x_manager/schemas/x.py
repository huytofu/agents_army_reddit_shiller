"""Dataclasses for X shiller graph state and DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


IdentityType = Literal["app_user", "blog_reader"]
PromoTarget = Literal["app", "blog", "none"]
PipelineDecisionType = Literal["browse", "browse_seeds", "reply", "post", "skip", "done"]
DraftKind = Literal["reply", "post"]
BrowseMode = Literal["search", "seeds"]


@dataclass
class IdentityCard:
    id: str
    display_name: str
    type: IdentityType
    background: str
    usage_or_reading_pattern: str
    core_purpose_or_topics: str
    favorite_features_or_angles: str
    voice: str
    search_queries: list[str]
    hashtags: list[str]
    seed_accounts: list[str]
    promo_bias: PromoTarget
    env_prefix: str
    system_prompt: str
    timezone_hint: str = "UTC"
    active: bool = True
    plan_tier: str = ""
    blog_topics: list[str] = field(default_factory=list)


@dataclass
class XCredentials:
    api_key: str
    api_secret: str
    access_token: str
    access_token_secret: str
    username: str = ""
    http_proxy: str = ""
    user_agent: str = ""


@dataclass
class BrowseItem:
    tweet_id: str
    author_username: str
    text: str
    like_count: int
    reply_count: int
    retweet_count: int
    created_at: float
    lang: str = "en"
    source: BrowseMode = "search"
    query: str = ""


@dataclass
class SelectedTarget:
    tweet_id: str
    author_username: str
    text: str
    like_count: int = 0
    source: BrowseMode = "search"
    query: str = ""


@dataclass
class DraftContent:
    kind: DraftKind
    body: str
    promote: bool = False
    promote_target: PromoTarget = "none"
    genuine_reply: bool = False
    hashtags: list[str] = field(default_factory=list)


@dataclass
class XPipelineDecision:
    decision: PipelineDecisionType
    reason: str = ""
    search_query: str = ""
    browse_mode: BrowseMode = "search"
    target_tweet_id: str = ""
    promote: bool = False
    promote_target: PromoTarget = "none"
    specialist_instructions: str = ""


@dataclass
class ActionLogEntry:
    timestamp: str
    action: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class XGraphState:
    identity: IdentityCard | None = None
    live: bool = False
    fast: bool = False
    run_id: str = ""
    artifacts_dir: str = ""
    browse_satisfied: bool = False
    browse_context: list[BrowseItem] = field(default_factory=list)
    selected_target: SelectedTarget | None = None
    pending_draft: DraftContent | None = None
    action_log: list[ActionLogEntry] = field(default_factory=list)
    main_decision: XPipelineDecision | None = None
    main_round: int = 0
    replies_this_run: int = 0
    posts_this_run: int = 0
    skip_after_browse: bool = False
    genuine_reply: bool = False
    errors: list[str] = field(default_factory=list)
    quota_snapshot: dict[str, Any] = field(default_factory=dict)


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

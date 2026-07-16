"""Dataclasses for Reddit shiller graph state and DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


IdentityType = Literal["app_user", "blog_reader"]
PromoTarget = Literal["app", "blog", "none"]
PipelineDecisionType = Literal["browse", "comment", "post", "skip", "done"]
DraftKind = Literal["comment", "post"]


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
    preferred_subreddits: list[str]
    promo_bias: PromoTarget
    env_prefix: str
    system_prompt: str
    timezone_hint: str = "UTC"
    active: bool = True
    plan_tier: str = ""
    blog_topics: list[str] = field(default_factory=list)


@dataclass
class RedditCredentials:
    client_id: str
    client_secret: str
    refresh_token: str
    username: str = ""
    http_proxy: str = ""
    user_agent: str = ""


@dataclass
class BrowseItem:
    post_id: str
    subreddit: str
    title: str
    snippet: str
    score: int
    num_comments: int
    sort: str
    created_utc: float
    permalink: str = ""
    top_comments: list[str] = field(default_factory=list)


@dataclass
class SelectedTarget:
    post_id: str
    subreddit: str
    title: str
    snippet: str
    sort: str
    reply_to_comment_id: str | None = None


@dataclass
class DraftContent:
    kind: DraftKind
    body: str
    title: str | None = None
    subreddit: str | None = None
    promote: bool = False
    promote_target: PromoTarget = "none"
    genuine_reply: bool = False


@dataclass
class RedditPipelineDecision:
    decision: PipelineDecisionType
    reason: str = ""
    subreddit: str = ""
    sort: str = "hot"
    target_post_id: str = ""
    promote: bool = False
    promote_target: PromoTarget = "none"
    specialist_instructions: str = ""


@dataclass
class ActionLogEntry:
    timestamp: str
    action: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RedditGraphState:
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
    main_decision: RedditPipelineDecision | None = None
    main_round: int = 0
    comments_this_run: int = 0
    posts_this_run: int = 0
    skip_after_browse: bool = False
    genuine_reply: bool = False
    errors: list[str] = field(default_factory=list)
    quota_snapshot: dict[str, Any] = field(default_factory=dict)


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

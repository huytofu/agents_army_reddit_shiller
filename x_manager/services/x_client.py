"""Tweepy X API v2 client with dry-run writes and fixture browse."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

from x_manager.config import X_CONFIG
from x_manager.schemas import BrowseItem, XCredentials

logger = logging.getLogger(__name__)

try:
    import tweepy  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    tweepy = None


FIXTURE_TWEETS = [
    {
        "tweet_id": "1900000000000000001",
        "author_username": "routine_seeker",
        "text": "Struggling to stay consistent with morning routines. Any tips that actually worked for you?",
        "like_count": 42,
        "reply_count": 18,
        "retweet_count": 3,
        "created_at": time.time() - 4 * 3600,
        "lang": "en",
        "query": "habit building",
    },
    {
        "tweet_id": "1900000000000000002",
        "author_username": "stoic_daily",
        "text": "How do you handle anger without suppressing it? Looking for practical frameworks.",
        "like_count": 89,
        "reply_count": 21,
        "retweet_count": 12,
        "created_at": time.time() - 9 * 3600,
        "lang": "en",
        "query": "stoicism",
    },
    {
        "tweet_id": "1900000000000000003",
        "author_username": "focus_lab",
        "text": "Day 12 of rebuilding focus habits and the mood swings are rough. Is this normal?",
        "like_count": 56,
        "reply_count": 44,
        "retweet_count": 5,
        "created_at": time.time() - 2 * 3600,
        "lang": "en",
        "query": "productivity tips",
    },
]


class XClientError(RuntimeError):
    pass


class XClient:
    def __init__(
        self,
        credentials: XCredentials | None = None,
        *,
        live: bool = False,
        user_agent: str | None = None,
    ):
        self.credentials = credentials
        self.live = live
        self.user_agent = (
            (credentials.user_agent if credentials and credentials.user_agent else None)
            or user_agent
            or X_CONFIG["USER_AGENT"]
        )
        self._client: Any | None = None
        self._use_fixtures = credentials is None or not _credentials_complete(credentials)

    def login(self) -> None:
        if self._use_fixtures:
            logger.info("Using fixture X browse (missing credentials).")
            return

        if tweepy is None:
            raise XClientError("tweepy is required for live X access.")

        assert self.credentials is not None
        # OAuth 1.0a user context (tweet/reply). Optional sticky proxy via requests session
        # is left to operator HTTP_PROXY env; Tweepy Client uses urllib3 under the hood.
        self._client = tweepy.Client(
            consumer_key=self.credentials.api_key,
            consumer_secret=self.credentials.api_secret,
            access_token=self.credentials.access_token,
            access_token_secret=self.credentials.access_token_secret,
            wait_on_rate_limit=True,
        )
        if self.credentials.http_proxy:
            logger.info(
                "Identity HTTP_PROXY set (%s); ensure process/env proxy is applied for outbound X traffic.",
                self.credentials.username or "unknown",
            )
        logger.info("Logged into X as %s", self.credentials.username or "unknown")

    def search_recent(self, query: str, *, max_results: int = 10) -> list[BrowseItem]:
        limit = max(10, min(max_results, 100))
        if self._use_fixtures or self._client is None:
            return _fixture_browse(query=query, source="search", limit=limit)

        try:
            response = self._client.search_recent_tweets(
                query=query,
                max_results=limit,
                tweet_fields=["created_at", "lang", "public_metrics", "author_id"],
                expansions=["author_id"],
                user_fields=["username"],
            )
            return _tweets_to_browse_items(response, query=query, source="search")
        except Exception as exc:
            logger.warning("Recent search failed for query=%s: %s", query, exc)
            return _fixture_browse(query=query, source="search", limit=limit)

    def get_user_timeline(self, username: str, *, max_results: int = 10) -> list[BrowseItem]:
        handle = username.lstrip("@")
        limit = max(5, min(max_results, 100))
        if self._use_fixtures or self._client is None:
            return _fixture_browse(query=f"from:{handle}", source="seeds", limit=limit)

        try:
            user = self._client.get_user(username=handle)
            if not user or not user.data:
                return []
            user_id = user.data.id
            response = self._client.get_users_tweets(
                id=user_id,
                max_results=limit,
                tweet_fields=["created_at", "lang", "public_metrics", "author_id"],
                exclude=["retweets", "replies"],
            )
            return _tweets_to_browse_items(
                response,
                query=f"from:{handle}",
                source="seeds",
                author_username=handle,
            )
        except Exception as exc:
            logger.warning("Timeline fetch failed for @%s: %s", handle, exc)
            return _fixture_browse(query=f"from:{handle}", source="seeds", limit=limit)

    def reply(self, tweet_id: str, text: str) -> dict[str, Any]:
        payload = {"tweet_id": tweet_id, "text": text}
        if not self.live:
            logger.info("Dry-run reply: %s", payload)
            return {"dry_run": True, **payload}

        if self._client is None:
            raise XClientError("Cannot reply without X login.")

        response = self._client.create_tweet(text=text, in_reply_to_tweet_id=tweet_id)
        tweet = getattr(response, "data", None) or {}
        return {"id": tweet.get("id", ""), "text": text, "in_reply_to": tweet_id}

    def post(self, text: str) -> dict[str, Any]:
        payload = {"text": text}
        if not self.live:
            logger.info("Dry-run post: %s", payload)
            return {"dry_run": True, **payload}

        if self._client is None:
            raise XClientError("Cannot post without X login.")

        response = self._client.create_tweet(text=text)
        tweet = getattr(response, "data", None) or {}
        return {"id": tweet.get("id", ""), "text": text}


def _credentials_complete(credentials: XCredentials) -> bool:
    return bool(
        credentials.api_key
        and credentials.api_secret
        and credentials.access_token
        and credentials.access_token_secret
    )


def _tweets_to_browse_items(
    response: Any,
    *,
    query: str,
    source: str,
    author_username: str = "",
) -> list[BrowseItem]:
    data = getattr(response, "data", None) or []
    includes = getattr(response, "includes", None) or {}
    users = {u.id: u for u in (includes.get("users") or [])}
    items: list[BrowseItem] = []
    for tweet in data:
        metrics = getattr(tweet, "public_metrics", None) or {}
        author = users.get(getattr(tweet, "author_id", None))
        username = author_username or (getattr(author, "username", "") if author else "unknown")
        created = getattr(tweet, "created_at", None)
        created_ts = created.timestamp() if created is not None else time.time()
        items.append(
            BrowseItem(
                tweet_id=str(tweet.id),
                author_username=str(username),
                text=str(getattr(tweet, "text", "") or "")[:500],
                like_count=int(metrics.get("like_count", 0) or 0),
                reply_count=int(metrics.get("reply_count", 0) or 0),
                retweet_count=int(metrics.get("retweet_count", 0) or 0),
                created_at=float(created_ts),
                lang=str(getattr(tweet, "lang", "en") or "en"),
                source=source,  # type: ignore[arg-type]
                query=query,
            )
        )
    return items


def _fixture_browse(*, query: str, source: str, limit: int) -> list[BrowseItem]:
    pool = [dict(item) for item in FIXTURE_TWEETS]
    random.shuffle(pool)
    items: list[BrowseItem] = []
    for raw in pool[:limit]:
        items.append(
            BrowseItem(
                tweet_id=str(raw["tweet_id"]),
                author_username=str(raw["author_username"]),
                text=str(raw["text"]),
                like_count=int(raw["like_count"]),
                reply_count=int(raw["reply_count"]),
                retweet_count=int(raw["retweet_count"]),
                created_at=float(raw["created_at"]),
                lang=str(raw["lang"]),
                source=source,  # type: ignore[arg-type]
                query=query or str(raw["query"]),
            )
        )
    return items

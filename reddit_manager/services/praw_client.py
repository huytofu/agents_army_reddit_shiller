"""PRAW Reddit client with dry-run writes and fixture browse."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

from reddit_manager.config import REDDIT_CONFIG
from reddit_manager.schemas import BrowseItem, RedditCredentials

logger = logging.getLogger(__name__)

try:
    import praw  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    praw = None


FIXTURE_POSTS = [
    {
        "post_id": "abc123",
        "subreddit": "getdisciplined",
        "title": "Struggling to stay consistent with morning routines",
        "snippet": "I keep falling off after a week. Any tips that actually worked for you?",
        "score": 142,
        "num_comments": 38,
        "sort": "hot",
        "created_utc": time.time() - 4 * 3600,
        "permalink": "/r/getdisciplined/comments/abc123/struggling/",
        "top_comments": ["Start embarrassingly small.", "Track streaks but forgive misses."],
    },
    {
        "post_id": "def456",
        "subreddit": "Stoicism",
        "title": "How do you handle anger without suppressing it?",
        "snippet": "I want to feel it but not act on it. Looking for practical frameworks.",
        "score": 89,
        "num_comments": 21,
        "sort": "new",
        "created_utc": time.time() - 9 * 3600,
        "permalink": "/r/Stoicism/comments/def456/how_do_you_handle_anger/",
        "top_comments": ["Name the emotion first.", "Pause before responding."],
    },
    {
        "post_id": "ghi789",
        "subreddit": "NoFap",
        "title": "Day 12 and mood swings are rough",
        "snippet": "Is this normal? Would love to hear how others got through the first month.",
        "score": 56,
        "num_comments": 44,
        "sort": "rising",
        "created_utc": time.time() - 2 * 3600,
        "permalink": "/r/NoFap/comments/ghi789/day_12/",
        "top_comments": ["Hydration and sleep helped me.", "Replace the habit loop with something else."],
    },
]


class RedditClientError(RuntimeError):
    pass


class RedditClient:
    def __init__(
        self,
        credentials: RedditCredentials | None = None,
        *,
        live: bool = False,
        user_agent: str | None = None,
    ):
        self.credentials = credentials
        self.live = live
        self.user_agent = (
            (credentials.user_agent if credentials and credentials.user_agent else None)
            or user_agent
            or REDDIT_CONFIG["USER_AGENT"]
        )
        self._reddit: Any | None = None
        self._use_fixtures = credentials is None or not _credentials_complete(credentials)

    def login(self) -> None:
        if self._use_fixtures:
            logger.info("Using fixture Reddit browse (missing credentials or dry-run browse mode).")
            return

        if praw is None:
            raise RedditClientError("praw is required for live Reddit access.")

        session_kwargs: dict[str, Any] = {}
        if self.credentials and self.credentials.http_proxy:
            import requests

            session = requests.Session()
            session.proxies.update(
                {
                    "http": self.credentials.http_proxy,
                    "https": self.credentials.http_proxy,
                }
            )
            session_kwargs["session"] = session

        assert self.credentials is not None
        self._reddit = praw.Reddit(
            client_id=self.credentials.client_id,
            client_secret=self.credentials.client_secret,
            refresh_token=self.credentials.refresh_token,
            user_agent=self.user_agent,
            requestor_kwargs=session_kwargs or None,
        )
        logger.info("Logged into Reddit as %s", self.credentials.username or "unknown")

    def browse_subreddit(self, subreddit: str, *, sort: str = "hot", limit: int = 10) -> list[BrowseItem]:
        if self._use_fixtures or self._reddit is None:
            return _fixture_browse(subreddit, sort=sort, limit=limit)

        try:
            sub = self._reddit.subreddit(subreddit)
            listing = _listing_for_sort(sub, sort)
            items: list[BrowseItem] = []
            for submission in listing.limit(limit):
                items.append(
                    BrowseItem(
                        post_id=str(submission.id),
                        subreddit=subreddit,
                        title=str(submission.title),
                        snippet=str(getattr(submission, "selftext", "") or "")[:500],
                        score=int(getattr(submission, "score", 0) or 0),
                        num_comments=int(getattr(submission, "num_comments", 0) or 0),
                        sort=sort,
                        created_utc=float(getattr(submission, "created_utc", time.time())),
                        permalink=f"https://reddit.com{submission.permalink}",
                    )
                )
            return items
        except Exception as exc:
            logger.warning("Browse failed for r/%s: %s", subreddit, exc)
            return _fixture_browse(subreddit, sort=sort, limit=limit)

    def submit_comment(self, post_id: str, body: str) -> dict[str, Any]:
        payload = {"post_id": post_id, "body": body}
        if not self.live:
            logger.info("Dry-run comment: %s", payload)
            return {"dry_run": True, **payload}

        if self._reddit is None:
            raise RedditClientError("Cannot submit comment without Reddit login.")

        submission = self._reddit.submission(id=post_id)
        comment = submission.reply(body)
        return {"id": comment.id, "permalink": f"https://reddit.com{comment.permalink}"}

    def submit_post(self, subreddit: str, title: str, body: str) -> dict[str, Any]:
        payload = {"subreddit": subreddit, "title": title, "body": body}
        if not self.live:
            logger.info("Dry-run post: %s", payload)
            return {"dry_run": True, **payload}

        if self._reddit is None:
            raise RedditClientError("Cannot submit post without Reddit login.")

        sub = self._reddit.subreddit(subreddit)
        submission = sub.submit(title=title, selftext=body)
        return {"id": submission.id, "permalink": f"https://reddit.com{submission.permalink}"}


def _credentials_complete(credentials: RedditCredentials) -> bool:
    return bool(credentials.client_id and credentials.client_secret and credentials.refresh_token)


def _listing_for_sort(subreddit: Any, sort: str):
    normalized = sort.lower()
    if normalized == "new":
        return subreddit.new
    if normalized == "rising":
        return subreddit.rising
    if normalized == "top":
        return subreddit.top(time_filter="day")
    return subreddit.hot


def _fixture_browse(subreddit: str, *, sort: str, limit: int) -> list[BrowseItem]:
    pool = [dict(item) for item in FIXTURE_POSTS]
    random.shuffle(pool)
    items: list[BrowseItem] = []
    for raw in pool[:limit]:
        items.append(
            BrowseItem(
                post_id=str(raw["post_id"]),
                subreddit=subreddit or str(raw["subreddit"]),
                title=str(raw["title"]),
                snippet=str(raw["snippet"]),
                score=int(raw["score"]),
                num_comments=int(raw["num_comments"]),
                sort=sort,
                created_utc=float(raw["created_utc"]),
                permalink=str(raw["permalink"]),
                top_comments=[str(c) for c in raw.get("top_comments", [])],
            )
        )
    return items

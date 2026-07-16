"""Randomized comment target selection."""

from __future__ import annotations

import random
import time

from reddit_manager.schemas import BrowseItem, SelectedTarget


def pick_comment_target(items: list[BrowseItem]) -> SelectedTarget | None:
    if not items:
        return None

    now = time.time()
    scored: list[tuple[float, BrowseItem]] = []
    for item in items:
        age_hours = max(0.1, (now - item.created_utc) / 3600.0)
        age_bonus = 1.0 if 1.0 <= age_hours <= 18.0 else 0.35
        engagement = min(item.score, 500) / 500.0
        noise = random.random() * 0.8
        score = age_bonus + engagement * 0.4 + noise
        scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top_pool = [item for _, item in scored[: max(3, len(scored) // 3)]]
    chosen = random.choice(top_pool)

    reply_to_comment_id = None
    if chosen.top_comments and random.random() < 0.25:
        reply_to_comment_id = f"comment-{random.randint(1, 999999)}"

    return SelectedTarget(
        post_id=chosen.post_id,
        subreddit=chosen.subreddit,
        title=chosen.title,
        snippet=chosen.snippet,
        sort=chosen.sort,
        reply_to_comment_id=reply_to_comment_id,
    )

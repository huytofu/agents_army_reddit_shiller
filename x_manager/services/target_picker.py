"""Randomized reply target selection for X tweets."""

from __future__ import annotations

import random
import time

from x_manager.schemas import BrowseItem, SelectedTarget


def pick_reply_target(items: list[BrowseItem]) -> SelectedTarget | None:
    """Prefer mid-engagement, recent, on-topic tweets — not always highest likes."""
    if not items:
        return None

    now = time.time()
    scored: list[tuple[float, BrowseItem]] = []
    for item in items:
        age_hours = max(0.1, (now - item.created_at) / 3600.0)
        age_bonus = 1.0 if 0.5 <= age_hours <= 24.0 else 0.35
        # Mid-engagement sweet spot: not dead, not mega-viral
        likes = item.like_count
        if 5 <= likes <= 200:
            engagement = 1.0
        elif likes < 5:
            engagement = 0.4
        else:
            engagement = 0.55
        noise = random.random() * 0.8
        score = age_bonus + engagement * 0.5 + noise
        scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top_pool = [item for _, item in scored[: max(3, len(scored) // 3)]]
    chosen = random.choice(top_pool)

    return SelectedTarget(
        tweet_id=chosen.tweet_id,
        author_username=chosen.author_username,
        text=chosen.text,
        like_count=chosen.like_count,
        source=chosen.source,
        query=chosen.query,
    )


# Back-compat alias during migration
pick_comment_target = pick_reply_target

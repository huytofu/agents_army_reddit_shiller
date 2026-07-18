"""Human-like delays and coin flips."""

from __future__ import annotations

import asyncio
import logging
import math
import random

from x_manager.config import HUMANIZATION_CONFIG

logger = logging.getLogger(__name__)


def should_skip_after_browse() -> bool:
    return random.random() < float(HUMANIZATION_CONFIG["P_SKIP"])


def should_genuine_reply() -> bool:
    """Reply-only gate: when True, force helpful reply with zero promo.

    Called from pick_target (reply path only). Never used for posts.
    """
    return random.random() < float(HUMANIZATION_CONFIG["P_GENUINE_REPLY"])


def should_allow_post() -> bool:
    """Ratio gate when supervisor chooses post — usually rewrite to reply.

    Default P_ALLOW_POST=0.1 → ~10% of post decisions proceed; rest become replies.
    Works with quota caps (MAX_POSTS_PER_RUN, weekly limits) for granular control.
    """
    return random.random() < float(HUMANIZATION_CONFIG["P_ALLOW_POST"])

def sample_posts_per_browse() -> int:
    low = int(HUMANIZATION_CONFIG["POSTS_PER_BROWSE_MIN"])
    high = int(HUMANIZATION_CONFIG["POSTS_PER_BROWSE_MAX"])
    return random.randint(low, max(low, high))


def sample_delay_seconds(*, fast: bool = False) -> float:
    if fast:
        return float(HUMANIZATION_CONFIG["FAST_DELAY_SEC"])

    mean = float(HUMANIZATION_CONFIG["DELAY_MEAN_SEC"])
    sigma = float(HUMANIZATION_CONFIG["DELAY_SIGMA"])
    low = float(HUMANIZATION_CONFIG["DELAY_MIN_SEC"])
    high = float(HUMANIZATION_CONFIG["DELAY_MAX_SEC"])
    value = random.lognormvariate(math.log(max(mean, 1.0)), sigma)
    return max(low, min(high, value))


async def human_wait(*, fast: bool = False) -> float:
    seconds = sample_delay_seconds(fast=fast)
    logger.info("Human wait sleeping for %.1f seconds (fast=%s)", seconds, fast)
    await asyncio.sleep(seconds)
    return seconds

"""Reddit shiller configuration."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from reddit_manager.constants import DEFAULT_ARTIFACTS_ROOT, DEFAULT_STATE_ROOT, DEFAULT_SUBREDDITS

if load_dotenv:
    load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _list_env(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return list(default or [])
    return [part.strip() for part in raw.split(",") if part.strip()]


SERVER_CONFIG = {
    "HOST": os.getenv("REDDIT_SHILLER_HOST", "0.0.0.0"),
    "PORT": _int_env("REDDIT_SHILLER_PORT", 7875),
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
}

LLM_CONFIG = {
    "TOGETHER_MODEL": os.getenv("REDDIT_TOGETHER_MODEL", ""),
    "HF_MODEL": os.getenv("REDDIT_HF_MODEL", ""),
    "HF_PROVIDER": os.getenv("REDDIT_HF_PROVIDER", "auto"),
    "HF_FALLBACK_MODEL_IDS": _list_env("REDDIT_HF_FALLBACK_MODEL_IDS"),
    "MAX_TOKENS": _int_env("REDDIT_LLM_MAX_TOKENS", 2048),
    "TEMPERATURE": _float_env("REDDIT_LLM_TEMPERATURE", 0.7),
    "TOP_P": _float_env("REDDIT_LLM_TOP_P", 0.9),
    "TIMEOUT_SEC": _int_env("REDDIT_LLM_TIMEOUT_SEC", 90),
    "DEBUG": _bool_env("REDDIT_LLM_DEBUG", False),
}

PIPELINE_LLM_CONFIG = {
    "TOGETHER_MODEL": os.getenv("REDDIT_PIPELINE_TOGETHER_MODEL", LLM_CONFIG["TOGETHER_MODEL"]),
    "HF_MODEL": os.getenv("REDDIT_PIPELINE_HF_MODEL", LLM_CONFIG["HF_MODEL"]),
    "HF_PROVIDER": os.getenv("REDDIT_PIPELINE_HF_PROVIDER", LLM_CONFIG["HF_PROVIDER"]),
    "HF_FALLBACK_MODEL_IDS": _list_env("REDDIT_PIPELINE_HF_FALLBACK_MODEL_IDS")
    or LLM_CONFIG["HF_FALLBACK_MODEL_IDS"],
    "MAX_TOKENS": _int_env("REDDIT_PIPELINE_LLM_MAX_TOKENS", LLM_CONFIG["MAX_TOKENS"]),
    "TEMPERATURE": _float_env("REDDIT_PIPELINE_LLM_TEMPERATURE", 0.2),
    "TOP_P": _float_env("REDDIT_PIPELINE_LLM_TOP_P", LLM_CONFIG["TOP_P"]),
    "TIMEOUT_SEC": _int_env("REDDIT_PIPELINE_LLM_TIMEOUT_SEC", LLM_CONFIG["TIMEOUT_SEC"]),
}

SPECIALIST_LLM_CONFIG = {
    "TOGETHER_MODEL": os.getenv("REDDIT_SPECIALIST_TOGETHER_MODEL", LLM_CONFIG["TOGETHER_MODEL"]),
    "HF_MODEL": os.getenv("REDDIT_SPECIALIST_HF_MODEL", LLM_CONFIG["HF_MODEL"]),
    "HF_PROVIDER": os.getenv("REDDIT_SPECIALIST_HF_PROVIDER", LLM_CONFIG["HF_PROVIDER"]),
    "HF_FALLBACK_MODEL_IDS": _list_env("REDDIT_SPECIALIST_HF_FALLBACK_MODEL_IDS")
    or LLM_CONFIG["HF_FALLBACK_MODEL_IDS"],
    "MAX_TOKENS": _int_env("REDDIT_SPECIALIST_LLM_MAX_TOKENS", LLM_CONFIG["MAX_TOKENS"]),
    "TEMPERATURE": _float_env("REDDIT_SPECIALIST_LLM_TEMPERATURE", 0.85),
    "TOP_P": _float_env("REDDIT_SPECIALIST_LLM_TOP_P", LLM_CONFIG["TOP_P"]),
    "TIMEOUT_SEC": _int_env("REDDIT_SPECIALIST_LLM_TIMEOUT_SEC", LLM_CONFIG["TIMEOUT_SEC"]),
}

REDDIT_CONFIG = {
    "USER_AGENT": os.getenv(
        "REDDIT_USER_AGENT",
        "EntourageRedditShiller/0.1 (by u/entourage-bot)",
    ),
    "ALLOW_NSFW": _bool_env("REDDIT_ALLOW_NSFW", False),
    "DEFAULT_SUBREDDITS": _list_env("REDDIT_DEFAULT_SUBREDDITS", DEFAULT_SUBREDDITS),
    "APP_URL": os.getenv("REDDIT_ENTOURAGE_APP_URL", "https://www.entourage-ai.life"),
    "BLOG_URL": os.getenv("REDDIT_ENTOURAGE_BLOG_URL", "https://www.entourage-ai.life/blogs.html"),
}

HUMANIZATION_CONFIG = {
    "P_SKIP": _float_env("REDDIT_P_SKIP", 0.2),
    "P_GENUINE_REPLY": _float_env("REDDIT_P_GENUINE_REPLY", 0.25),
    "P_ALLOW_POST": _float_env("REDDIT_P_ALLOW_POST", 0.1),
    "DELAY_MEAN_SEC": _float_env("REDDIT_DELAY_MEAN_SEC", 90.0),
    "DELAY_SIGMA": _float_env("REDDIT_DELAY_SIGMA", 0.6),
    "DELAY_MIN_SEC": _float_env("REDDIT_DELAY_MIN_SEC", 30.0),
    "DELAY_MAX_SEC": _float_env("REDDIT_DELAY_MAX_SEC", 480.0),
    "FAST_DELAY_SEC": _float_env("REDDIT_FAST_DELAY_SEC", 0.5),
    "POSTS_PER_BROWSE_MIN": _int_env("REDDIT_POSTS_PER_BROWSE_MIN", 8),
    "POSTS_PER_BROWSE_MAX": _int_env("REDDIT_POSTS_PER_BROWSE_MAX", 12),
    "COMMENTS_TO_READ_MIN": _int_env("REDDIT_COMMENTS_TO_READ_MIN", 1),
    "COMMENTS_TO_READ_MAX": _int_env("REDDIT_COMMENTS_TO_READ_MAX", 3),
}

QUOTA_CONFIG = {
    "MAX_RUNS_PER_IDENTITY_PER_DAY": _int_env("REDDIT_MAX_RUNS_PER_IDENTITY_PER_DAY", 1),
    "MAX_GLOBAL_RUNS_PER_DAY": _int_env("REDDIT_MAX_GLOBAL_RUNS_PER_DAY", 3),
    "MAX_COMMENTS_PER_IDENTITY_PER_DAY": _int_env("REDDIT_MAX_COMMENTS_PER_IDENTITY_PER_DAY", 2),
    "MAX_POSTS_PER_IDENTITY_PER_DAY": _int_env("REDDIT_MAX_POSTS_PER_IDENTITY_PER_DAY", 0),
    "MAX_POSTS_PER_IDENTITY_PER_WEEK": _int_env("REDDIT_MAX_POSTS_PER_IDENTITY_PER_WEEK", 1),
    "MAX_COMMENTS_PER_DAY_GLOBAL": _int_env("REDDIT_MAX_COMMENTS_PER_DAY_GLOBAL", 5),
    "MAX_POSTS_PER_DAY_GLOBAL": _int_env("REDDIT_MAX_POSTS_PER_DAY_GLOBAL", 1),
    "MAX_COMMENTS_PER_RUN": _int_env("REDDIT_MAX_COMMENTS_PER_RUN", 1),
    "MAX_POSTS_PER_RUN": _int_env("REDDIT_MAX_POSTS_PER_RUN", 0),
    "MIN_HOURS_BETWEEN_IDENTITIES": _float_env("REDDIT_MIN_HOURS_BETWEEN_IDENTITIES", 4.0),
    "MAX_DOMAIN_LINKS_PER_WEEK": _int_env("REDDIT_MAX_DOMAIN_LINKS_PER_WEEK", 2),
    "PROMO_MAX_RATIO": _float_env("REDDIT_PROMO_MAX_RATIO", 0.25),
    "RATE_LIMIT_COOLDOWN_HOURS": _float_env("REDDIT_RATE_LIMIT_COOLDOWN_HOURS", 24.0),
}

WORKER_CONFIG = {
    "DRY_RUN": _bool_env("REDDIT_DRY_RUN", True),
    "MAIN_AGENT_MAX_ROUNDS": _int_env("REDDIT_MAIN_AGENT_MAX_ROUNDS", 5),
    "ARTIFACTS_ROOT": os.getenv("REDDIT_ARTIFACTS_ROOT", DEFAULT_ARTIFACTS_ROOT),
    "STATE_ROOT": os.getenv("REDDIT_STATE_ROOT", DEFAULT_STATE_ROOT),
    "SCHEDULER_MIN_HOURS": _float_env("REDDIT_SCHEDULER_MIN_HOURS", 4.0),
    "SCHEDULER_MAX_HOURS": _float_env("REDDIT_SCHEDULER_MAX_HOURS", 48.0),
}


def get_together_token() -> str:
    return os.getenv("REDDIT_TOGETHER_API_KEY", os.getenv("TOGETHER_API_KEY", ""))


def get_hf_token() -> str:
    return os.getenv("REDDIT_HUGGINGFACE_API_KEY", os.getenv("HUGGINGFACE_API_KEY", ""))


def get_identity_reddit_credentials(env_prefix: str) -> dict[str, str]:
    """Resolve OAuth and optional proxy env vars for one persona."""
    prefix = env_prefix.strip().upper()
    return {
        "client_id": os.getenv(f"REDDIT_{prefix}_CLIENT_ID", ""),
        "client_secret": os.getenv(f"REDDIT_{prefix}_CLIENT_SECRET", ""),
        "refresh_token": os.getenv(f"REDDIT_{prefix}_REFRESH_TOKEN", ""),
        "username": os.getenv(f"REDDIT_{prefix}_USERNAME", ""),
        "http_proxy": os.getenv(f"REDDIT_{prefix}_HTTP_PROXY", ""),
        "user_agent": os.getenv(
            f"REDDIT_{prefix}_USER_AGENT",
            os.getenv("REDDIT_USER_AGENT", ""),
        ),
    }

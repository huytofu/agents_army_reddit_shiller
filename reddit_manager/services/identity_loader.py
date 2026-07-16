"""Load persona YAML cards and pick an identity for a run."""

from __future__ import annotations

import random
from pathlib import Path

import yaml

from reddit_manager.config import get_identity_reddit_credentials
from reddit_manager.schemas import IdentityCard, RedditCredentials


class IdentityLoaderError(RuntimeError):
    pass


def identities_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "identities"


def load_identity(path: Path) -> IdentityCard:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise IdentityLoaderError(f"Invalid identity file: {path}")

    promo_bias = str(data.get("promo_bias", "app")).lower()
    if promo_bias not in {"app", "blog", "none"}:
        promo_bias = "app"

    identity_type = str(data.get("type", "app_user"))
    if identity_type not in {"app_user", "blog_reader"}:
        identity_type = "app_user"

    return IdentityCard(
        id=str(data["id"]),
        display_name=str(data.get("display_name", data["id"])),
        type=identity_type,  # type: ignore[arg-type]
        background=str(data.get("background", "")),
        usage_or_reading_pattern=str(data.get("usage_or_reading_pattern", "")),
        core_purpose_or_topics=str(data.get("core_purpose_or_topics", "")),
        favorite_features_or_angles=str(data.get("favorite_features_or_angles", "")),
        voice=str(data.get("voice", "")),
        preferred_subreddits=[str(s) for s in data.get("preferred_subreddits", [])],
        promo_bias=promo_bias,  # type: ignore[arg-type]
        env_prefix=str(data.get("env_prefix", data["id"]).upper()),
        system_prompt=str(data.get("system_prompt", "")),
        timezone_hint=str(data.get("timezone_hint", "UTC")),
        active=bool(data.get("active", True)),
        plan_tier=str(data.get("plan_tier", "")),
        blog_topics=[str(t) for t in data.get("blog_topics", [])],
    )


def list_identities(*, active_only: bool = True) -> list[IdentityCard]:
    directory = identities_dir()
    if not directory.exists():
        return []
    cards: list[IdentityCard] = []
    for path in sorted(directory.glob("*.yaml")):
        card = load_identity(path)
        if active_only and not card.active:
            continue
        cards.append(card)
    return cards


def list_all_identities() -> list[IdentityCard]:
    return list_identities(active_only=False)


def get_identity(identity_id: str) -> IdentityCard:
    for card in list_all_identities():
        if card.id == identity_id:
            if not card.active:
                raise IdentityLoaderError(
                    f"Identity '{identity_id}' is deactivated (planned feature not released yet)."
                )
            return card
    raise IdentityLoaderError(f"Unknown identity: {identity_id}")


def pick_identity(
    identity_id: str | None = None,
    *,
    require_credentials: bool = False,
) -> IdentityCard:
    if identity_id:
        return get_identity(identity_id)

    candidates = list_identities()
    if not candidates:
        raise IdentityLoaderError("No identity YAML files found.")

    if require_credentials:
        credentialed = [c for c in candidates if _has_credentials(c)]
        if not credentialed:
            raise IdentityLoaderError("No identities with OAuth credentials configured.")
        return random.choice(credentialed)

    return random.choice(candidates)


def resolve_credentials(identity: IdentityCard) -> RedditCredentials:
    raw = get_identity_reddit_credentials(identity.env_prefix)
    return RedditCredentials(
        client_id=raw["client_id"],
        client_secret=raw["client_secret"],
        refresh_token=raw["refresh_token"],
        username=raw["username"],
        http_proxy=raw["http_proxy"],
        user_agent=raw.get("user_agent", ""),
    )


def _has_credentials(identity: IdentityCard) -> bool:
    creds = resolve_credentials(identity)
    return bool(creds.client_id and creds.client_secret and creds.refresh_token)

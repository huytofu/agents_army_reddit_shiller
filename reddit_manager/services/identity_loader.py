"""Load persona YAML cards and pick an identity for a run."""

from __future__ import annotations

import random
from functools import lru_cache
from pathlib import Path

import yaml

from reddit_manager.config import get_identity_reddit_credentials
from reddit_manager.schemas import IdentityCard, RedditCredentials

ACTIVATION_FILENAME = "activation.yaml"


class IdentityLoaderError(RuntimeError):
    pass


def identities_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "identities"


@lru_cache(maxsize=1)
def load_activation_roster() -> dict:
    path = identities_dir() / ACTIVATION_FILENAME
    if not path.exists():
        return {"active_ids": set(), "deactivated_ids": set(), "raw": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    active_ids: set[str] = set()
    deactivated_ids: set[str] = set()
    for group in (data.get("active") or {}).values():
        active_ids.update(str(x) for x in (group or []))
    for group in (data.get("deactivated") or {}).values():
        deactivated_ids.update(str(x) for x in (group or []))
    return {"active_ids": active_ids, "deactivated_ids": deactivated_ids, "raw": data}


def clear_activation_cache() -> None:
    load_activation_roster.cache_clear()


def is_identity_active(identity_id: str) -> bool:
    roster = load_activation_roster()
    return identity_id in roster["active_ids"]


def load_identity(path: Path) -> IdentityCard:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise IdentityLoaderError(f"Invalid identity file: {path}")
    if "id" not in data:
        raise IdentityLoaderError(f"Not an identity card (missing id): {path}")

    promo_bias = str(data.get("promo_bias", "app")).lower()
    if promo_bias not in {"app", "blog", "none"}:
        promo_bias = "app"

    identity_type = str(data.get("type", "app_user"))
    if identity_type not in {"app_user", "blog_reader"}:
        identity_type = "app_user"

    identity_id = str(data["id"])
    # activation.yaml is source of truth; YAML active: is documentation only
    active = is_identity_active(identity_id)

    return IdentityCard(
        id=identity_id,
        display_name=str(data.get("display_name", identity_id)),
        type=identity_type,  # type: ignore[arg-type]
        background=str(data.get("background", "")),
        usage_or_reading_pattern=str(data.get("usage_or_reading_pattern", "")),
        core_purpose_or_topics=str(data.get("core_purpose_or_topics", "")),
        favorite_features_or_angles=str(data.get("favorite_features_or_angles", "")),
        voice=str(data.get("voice", "")),
        preferred_subreddits=[str(s) for s in data.get("preferred_subreddits", [])],
        promo_bias=promo_bias,  # type: ignore[arg-type]
        env_prefix=str(data.get("env_prefix", identity_id).upper()),
        system_prompt=str(data.get("system_prompt", "")),
        timezone_hint=str(data.get("timezone_hint", "UTC")),
        active=active,
        plan_tier=str(data.get("plan_tier", "")),
        blog_topics=[str(t) for t in data.get("blog_topics", [])],
    )


def _identity_card_paths() -> list[Path]:
    directory = identities_dir()
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.glob("*.yaml")
        if path.name != ACTIVATION_FILENAME
    )


def list_identities(*, active_only: bool = True) -> list[IdentityCard]:
    cards: list[IdentityCard] = []
    for path in _identity_card_paths():
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
                    f"Identity '{identity_id}' is deactivated. "
                    f"Move it under active in identities/{ACTIVATION_FILENAME} when credentials are ready."
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
        raise IdentityLoaderError("No active identities configured in activation.yaml.")

    if require_credentials:
        credentialed = [c for c in candidates if _has_credentials(c)]
        if not credentialed:
            raise IdentityLoaderError("No active identities with OAuth credentials configured.")
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

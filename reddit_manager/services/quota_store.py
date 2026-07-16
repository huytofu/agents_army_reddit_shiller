"""Local JSON quota and run state store."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from reddit_manager.config import QUOTA_CONFIG, WORKER_CONFIG

logger = logging.getLogger(__name__)


class QuotaStore:
    def __init__(self, root: str | None = None):
        self.root = Path(root or WORKER_CONFIG["STATE_ROOT"])
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "quota_state.json"
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"global": {}, "identities": {}, "host": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _week(self) -> str:
        return datetime.now(timezone.utc).strftime("%G-W%V")

    def _ensure_identity(self, identity_id: str) -> dict[str, Any]:
        identities = self._data.setdefault("identities", {})
        return identities.setdefault(
            identity_id,
            {
                "runs_today": 0,
                "comments_today": 0,
                "posts_today": 0,
                "posts_week": 0,
                "links_week": 0,
                "last_run_at": "",
                "next_eligible_at": "",
                "last_subreddits": [],
                "last_draft_fingerprints": [],
                "cooldown_until": "",
                "day_key": self._today(),
                "week_key": self._week(),
            },
        )

    def _reset_daily_if_needed(self, record: dict[str, Any]) -> None:
        today = self._today()
        if record.get("day_key") != today:
            record["day_key"] = today
            record["runs_today"] = 0
            record["comments_today"] = 0
            record["posts_today"] = 0

    def _reset_weekly_if_needed(self, record: dict[str, Any]) -> None:
        week = self._week()
        if record.get("week_key") != week:
            record["week_key"] = week
            record["posts_week"] = 0
            record["links_week"] = 0

    def can_start_run(self, identity_id: str, *, force: bool = False) -> tuple[bool, str]:
        if force:
            return True, "forced"

        record = self._ensure_identity(identity_id)
        self._reset_daily_if_needed(record)
        global_record = self._data.setdefault("global", {})
        if global_record.get("day_key") != self._today():
            global_record["day_key"] = self._today()
            global_record["runs_today"] = 0
            global_record["comments_today"] = 0
            global_record["posts_today"] = 0

        cooldown_until = record.get("cooldown_until", "")
        if cooldown_until:
            if datetime.fromisoformat(cooldown_until.replace("Z", "+00:00")) > datetime.now(timezone.utc):
                return False, f"identity cooldown active until {cooldown_until}"

        next_eligible = record.get("next_eligible_at", "")
        if next_eligible:
            if datetime.fromisoformat(next_eligible.replace("Z", "+00:00")) > datetime.now(timezone.utc):
                return False, f"next eligible at {next_eligible}"

        if record["runs_today"] >= QUOTA_CONFIG["MAX_RUNS_PER_IDENTITY_PER_DAY"]:
            return False, "identity daily run limit reached"

        if global_record.get("runs_today", 0) >= QUOTA_CONFIG["MAX_GLOBAL_RUNS_PER_DAY"]:
            return False, "global daily run limit reached"

        host = self._data.setdefault("host", {})
        last_host_identity = host.get("last_identity_id", "")
        last_host_at = host.get("last_run_at", "")
        if last_host_identity and last_host_identity != identity_id and last_host_at:
            min_gap = timedelta(hours=float(QUOTA_CONFIG["MIN_HOURS_BETWEEN_IDENTITIES"]))
            if datetime.now(timezone.utc) - datetime.fromisoformat(last_host_at.replace("Z", "+00:00")) < min_gap:
                return False, "host identity cooldown active"

        return True, "ok"

    def can_comment(self, identity_id: str) -> tuple[bool, str]:
        record = self._ensure_identity(identity_id)
        self._reset_daily_if_needed(record)
        global_record = self._data.setdefault("global", {})
        if global_record.get("day_key") != self._today():
            global_record["day_key"] = self._today()
            global_record["comments_today"] = 0

        if record["comments_today"] >= QUOTA_CONFIG["MAX_COMMENTS_PER_IDENTITY_PER_DAY"]:
            return False, "identity comment daily limit"
        if global_record.get("comments_today", 0) >= QUOTA_CONFIG["MAX_COMMENTS_PER_DAY_GLOBAL"]:
            return False, "global comment daily limit"
        return True, "ok"

    def can_post(self, identity_id: str) -> tuple[bool, str]:
        record = self._ensure_identity(identity_id)
        self._reset_daily_if_needed(record)
        self._reset_weekly_if_needed(record)
        global_record = self._data.setdefault("global", {})
        if global_record.get("day_key") != self._today():
            global_record["day_key"] = self._today()
            global_record["posts_today"] = 0

        if record["posts_today"] >= QUOTA_CONFIG["MAX_POSTS_PER_IDENTITY_PER_DAY"]:
            return False, "identity post daily limit"
        if record["posts_week"] >= QUOTA_CONFIG["MAX_POSTS_PER_IDENTITY_PER_WEEK"]:
            return False, "identity post weekly limit"
        if global_record.get("posts_today", 0) >= QUOTA_CONFIG["MAX_POSTS_PER_DAY_GLOBAL"]:
            return False, "global post daily limit"
        return True, "ok"

    def record_run_start(self, identity_id: str) -> None:
        record = self._ensure_identity(identity_id)
        self._reset_daily_if_needed(record)
        record["runs_today"] += 1
        record["last_run_at"] = _utc_now()

        global_record = self._data.setdefault("global", {})
        if global_record.get("day_key") != self._today():
            global_record["day_key"] = self._today()
            global_record["runs_today"] = 0
        global_record["runs_today"] = global_record.get("runs_today", 0) + 1

        host = self._data.setdefault("host", {})
        host["last_identity_id"] = identity_id
        host["last_run_at"] = _utc_now()
        self.save()

    def record_comment(self, identity_id: str) -> None:
        record = self._ensure_identity(identity_id)
        self._reset_daily_if_needed(record)
        record["comments_today"] += 1
        global_record = self._data.setdefault("global", {})
        global_record["comments_today"] = global_record.get("comments_today", 0) + 1
        self.save()

    def record_post(self, identity_id: str) -> None:
        record = self._ensure_identity(identity_id)
        self._reset_daily_if_needed(record)
        self._reset_weekly_if_needed(record)
        record["posts_today"] += 1
        record["posts_week"] += 1
        global_record = self._data.setdefault("global", {})
        global_record["posts_today"] = global_record.get("posts_today", 0) + 1
        self.save()

    def record_link(self, identity_id: str) -> None:
        record = self._ensure_identity(identity_id)
        self._reset_weekly_if_needed(record)
        record["links_week"] += 1
        self.save()

    def can_include_link(self, identity_id: str) -> bool:
        record = self._ensure_identity(identity_id)
        self._reset_weekly_if_needed(record)
        return record["links_week"] < QUOTA_CONFIG["MAX_DOMAIN_LINKS_PER_WEEK"]

    def set_next_eligible_at(self, identity_id: str, when_iso: str) -> None:
        record = self._ensure_identity(identity_id)
        record["next_eligible_at"] = when_iso
        self.save()

    def set_cooldown(self, identity_id: str, hours: float) -> None:
        record = self._ensure_identity(identity_id)
        until = datetime.now(timezone.utc) + timedelta(hours=hours)
        record["cooldown_until"] = until.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self.save()

    def remember_subreddit(self, identity_id: str, subreddit: str) -> None:
        record = self._ensure_identity(identity_id)
        recent = [s for s in record.get("last_subreddits", []) if s != subreddit]
        record["last_subreddits"] = [subreddit, *recent][:5]
        self.save()

    def get_snapshot(self, identity_id: str) -> dict[str, Any]:
        record = self._ensure_identity(identity_id)
        self._reset_daily_if_needed(record)
        self._reset_weekly_if_needed(record)
        global_record = self._data.setdefault("global", {})
        return {
            "identity": dict(record),
            "global": dict(global_record),
            "limits": dict(QUOTA_CONFIG),
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

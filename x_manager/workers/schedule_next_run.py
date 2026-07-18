"""Print or wait until the next irregular run slot."""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import datetime, timezone

from x_manager.services.identity_loader import list_identities
from x_manager.services.quota_store import QuotaStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or wait for next eligible X shill run.")
    parser.add_argument("--identity", help="Identity id to inspect.")
    parser.add_argument("--sleep", action="store_true", help="Sleep until next_eligible_at (if set).")
    args = parser.parse_args()

    store = QuotaStore()
    identities = [i for i in list_identities() if not args.identity or i.id == args.identity]
    for identity in identities:
        snap = store.get_snapshot(identity.id)
        next_at = snap["identity"].get("next_eligible_at", "")
        print(f"{identity.id}: next_eligible_at={next_at or 'unset'}")
        if args.sleep and next_at:
            target = datetime.fromisoformat(next_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if target > now:
                seconds = (target - now).total_seconds()
                print(f"Sleeping {seconds:.0f}s for {identity.id}")
                time.sleep(seconds)


if __name__ == "__main__":
    main()

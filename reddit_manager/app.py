"""Dormant FastAPI marker — Reddit shiller is CLI-first in v1."""

from __future__ import annotations


def create_app():
    raise RuntimeError("Reddit shiller is CLI-first; use reddit_manager.workers.run_shill_job.")

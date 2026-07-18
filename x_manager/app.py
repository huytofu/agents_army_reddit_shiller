"""Dormant FastAPI marker — X shiller is CLI-first in v1."""

from __future__ import annotations


def create_app():
    raise RuntimeError("X shiller is CLI-first; use x_manager.workers.run_shill_job.")

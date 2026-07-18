"""Load shared prompt text."""

from __future__ import annotations

from pathlib import Path


def load_shared_guidelines() -> str:
    path = Path(__file__).resolve().parent / "shared_guidelines.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()

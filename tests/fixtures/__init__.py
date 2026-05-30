"""Fixture helpers for tests and mock-mode development plumbing."""

import json
from pathlib import Path
from typing import Any


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture by path relative to tests/fixtures."""

    fixture_path = Path(__file__).resolve().parent / name
    return json.loads(fixture_path.read_text(encoding="utf-8"))

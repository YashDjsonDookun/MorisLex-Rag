"""Optional run control for pipeline stop (mirror engine pattern)."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_config

RUN_CONTROL_FILENAME = "run_control.json"


def run_control_path() -> Path:
    return get_config().state_path / RUN_CONTROL_FILENAME


def request_stop() -> None:
    """Set run_control to request stop."""
    p = run_control_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"stop_requested": True}), encoding="utf-8")


def clear_stop() -> None:
    """Clear stop request."""
    p = run_control_path()
    if p.exists():
        p.write_text(json.dumps({"stop_requested": False}), encoding="utf-8")


def stop_requested() -> bool:
    """Return True if stop was requested."""
    p = run_control_path()
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("stop_requested", False)
    except (json.JSONDecodeError, OSError):
        return False

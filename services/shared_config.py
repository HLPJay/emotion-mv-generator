from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "model_config.json"

_cached_config: dict[str, Any] = {}
_cached_mtime: float | None = None


def _load_raw_config() -> dict[str, Any]:
    """Load and cache the raw config JSON, reloading if the file has been modified."""
    global _cached_config, _cached_mtime

    if not CONFIG_PATH.exists():
        _cached_config = {}
        _cached_mtime = None
        return {}

    mtime = CONFIG_PATH.stat().st_mtime
    if _cached_mtime == mtime:
        return _cached_config

    try:
        with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
            _cached_config = json.load(file)
            _cached_mtime = mtime
            return _cached_config
    except (json.JSONDecodeError, OSError):
        return _cached_config or {}


def get_llm_config() -> dict[str, Any]:
    return _load_raw_config()


def get_image_config() -> dict[str, Any]:
    return _load_raw_config().get("image", {})


def get_audio_config() -> dict[str, Any]:
    return _load_raw_config().get("audio", {})


def get_video_config() -> dict[str, Any]:
    return _load_raw_config().get("video", {})

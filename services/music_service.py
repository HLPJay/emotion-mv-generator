from __future__ import annotations

import json
from pathlib import Path
import time

import requests


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "model_config.json"
AUDIO_DIR = ROOT / "generated" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


class MusicGenerationError(RuntimeError):
    pass


def _config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def _music_config() -> dict:
    config = _config()
    music_config = config.get("music", {})
    fallback_models = music_config.get("fallback_models", [])
    if isinstance(fallback_models, str):
        fallback_models = [fallback_models]
    return {
        "enabled": bool(music_config.get("enabled", False)),
        "provider": music_config.get("provider", "minimax"),
        "api_base": music_config.get("api_base", "https://api.minimaxi.com"),
        "model": music_config.get("model", "music-2.6"),
        "api_key": music_config.get("api_key") or config.get("api_key", ""),
        "output_format": music_config.get("output_format", "hex"),
        "fallback_on_error": bool(music_config.get("fallback_on_error", True)),
        "fallback_models": [model for model in fallback_models if model],
        "request_timeout_seconds": int(music_config.get("request_timeout_seconds", 600)),
        "retry_attempts": max(1, int(music_config.get("retry_attempts", 3))),
        "retry_backoff_seconds": music_config.get("retry_backoff_seconds", [5, 15]),
    }


def music_enabled() -> bool:
    return bool(_music_config()["enabled"])


def _request_music(config: dict, music_plan: dict, model: str, output_dir: Path) -> Path:
    url = f"{config['api_base'].rstrip('/')}/v1/music_generation"
    payload = {
        "model": model,
        "prompt": music_plan["prompt"],
        "stream": False,
        "output_format": config["output_format"],
        "aigc_watermark": False,
        "lyrics_optimizer": False,
        "is_instrumental": True,
        "audio_setting": {
            "sample_rate": 44100,
            "bitrate": 256000,
            "format": "mp3",
        },
    }
    headers = {
        "Authorization": f"Bearer {config['api_key'].strip()}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=config["request_timeout_seconds"])
    if response.status_code >= 400:
        raise MusicGenerationError(f"MiniMax music request failed: {response.status_code} {response.text}")

    data = response.json()
    if data.get("base_resp", {}).get("status_code") not in (None, 0):
        raise MusicGenerationError(f"MiniMax music generation failed: {data}")

    output_dir = output_dir or AUDIO_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "bgm.mp3"
    result_data = data.get("data") or {}
    if config["output_format"] == "url":
        audio_url = result_data.get("audio")
        if not audio_url:
            raise MusicGenerationError(f"MiniMax music response missing audio url: {data}")
        audio_response = requests.get(audio_url, timeout=120)
        audio_response.raise_for_status()
        output.write_bytes(audio_response.content)
        return output

    audio_hex = result_data.get("audio")
    if not audio_hex:
        raise MusicGenerationError(f"MiniMax music response missing audio data: {data}")
    output.write_bytes(bytes.fromhex(audio_hex))
    return output


def _retry_delay(config: dict, attempt_index: int) -> float:
    backoff = config.get("retry_backoff_seconds", [5, 15])
    if isinstance(backoff, (int, float)):
        return float(backoff)
    if isinstance(backoff, list) and backoff:
        return float(backoff[min(attempt_index, len(backoff) - 1)])
    return float(5 * (attempt_index + 1))


def _is_retryable_music_error(exc: Exception) -> bool:
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.ProxyError)):
        return True
    message = str(exc).lower()
    retryable_markers = [
        "remote end closed connection",
        "connection aborted",
        "connection reset",
        "temporarily unavailable",
        "timeout",
        "too many requests",
        "502",
        "503",
        "504",
    ]
    return any(marker in message for marker in retryable_markers)


def _candidate_models(requested_model: str) -> list[str]:
    candidates = [requested_model]
    unique = []
    for model in candidates:
        if model and model not in unique:
            unique.append(model)
    return unique


def generate_music_audio(audio_plan: dict, output_dir: Path | None = None) -> Path | None:
    config = _music_config()
    if not config["enabled"]:
        return None

    api_key = config["api_key"].strip()
    if not api_key:
        raise MusicGenerationError("Missing music API key. Set music.api_key or top-level api_key in config/model_config.json.")

    music_plan = audio_plan.get("music", {})
    prompt = music_plan.get("prompt", "").strip()
    if not prompt:
        return None

    output_dir = output_dir or AUDIO_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    request_plan = dict(music_plan)
    request_plan["prompt"] = prompt

    requested_model = music_plan.get("model", config["model"])
    errors = []
    candidate_models = _candidate_models(requested_model)
    if config["fallback_on_error"]:
        candidate_models.extend(model for model in config["fallback_models"] if model not in candidate_models)

    for model in candidate_models:
        for attempt in range(config["retry_attempts"]):
            try:
                return _request_music(config, request_plan, model, output_dir)
            except Exception as exc:
                attempt_label = f"attempt {attempt + 1}/{config['retry_attempts']}"
                errors.append(f"{model} {attempt_label}: {exc}")
                if attempt + 1 >= config["retry_attempts"] or not _is_retryable_music_error(exc):
                    break
                time.sleep(_retry_delay(config, attempt))
        if not config["fallback_on_error"]:
            break

    raise MusicGenerationError("MiniMax music generation failed for all candidate models: " + " | ".join(errors))

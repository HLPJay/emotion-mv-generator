from __future__ import annotations

import json
from pathlib import Path

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
    return {
        "enabled": bool(music_config.get("enabled", False)),
        "provider": music_config.get("provider", "minimax"),
        "api_base": music_config.get("api_base", "https://api.minimaxi.com"),
        "model": music_config.get("model", "music-2.6"),
        "api_key": music_config.get("api_key") or config.get("api_key", ""),
        "output_format": music_config.get("output_format", "hex"),
        "fallback_on_error": bool(music_config.get("fallback_on_error", True)),
    }


def music_enabled() -> bool:
    return bool(_music_config()["enabled"])


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

    url = f"{config['api_base'].rstrip('/')}/v1/music_generation"
    payload = {
        "model": music_plan.get("model", config["model"]),
        "prompt": prompt,
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
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=240)
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

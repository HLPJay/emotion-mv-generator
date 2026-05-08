from __future__ import annotations

import json
from pathlib import Path

import requests

from services.audio_plan_service import narration_text_from_audio_plan


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "model_config.json"
AUDIO_DIR = ROOT / "generated" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


class AudioGenerationError(RuntimeError):
    pass


def _config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def _audio_config() -> dict:
    config = _config()
    audio_config = config.get("audio", {})
    return {
        "enabled": bool(audio_config.get("enabled", False)),
        "provider": audio_config.get("provider", config.get("provider", "minimax")),
        "api_base": audio_config.get("api_base", "https://api.minimaxi.com"),
        "model": audio_config.get("model", "speech-2.8-hd"),
        "api_key": audio_config.get("api_key") or config.get("api_key", ""),
        "voice_id": audio_config.get("voice_id", "male-qn-qingse"),
        "speed": float(audio_config.get("speed", 0.88)),
        "vol": float(audio_config.get("vol", 1.0)),
        "pitch": int(audio_config.get("pitch", -1)),
        "emotion": audio_config.get("emotion", "sad"),
        "output_format": audio_config.get("output_format", "hex"),
        "fallback_on_error": bool(audio_config.get("fallback_on_error", True)),
    }


def narration_enabled() -> bool:
    return bool(_audio_config()["enabled"])


def _narration_text(storyboard: list[dict]) -> str:
    lines = []
    for shot in storyboard:
        subtitle = shot.get("subtitle", "").strip()
        if not subtitle or subtitle == "...":
            lines.append("<#1.0#>")
            continue
        lines.append(subtitle.rstrip("。！？!?，,") + "。")
    return "\n".join(lines).strip()


def generate_narration_audio(storyboard_or_audio_plan, output_dir: Path | None = None) -> Path | None:
    config = _audio_config()
    if not config["enabled"]:
        return None

    api_key = config["api_key"].strip()
    if not api_key:
        raise AudioGenerationError("Missing audio API key. Set audio.api_key or top-level api_key in config/model_config.json.")

    if isinstance(storyboard_or_audio_plan, dict) and "narration" in storyboard_or_audio_plan:
        text = narration_text_from_audio_plan(storyboard_or_audio_plan)
        voice_plan = storyboard_or_audio_plan.get("voice", {})
    else:
        text = _narration_text(storyboard_or_audio_plan)
        voice_plan = {}
    if not text:
        return None

    url = f"{config['api_base'].rstrip('/')}/v1/t2a_v2"
    payload = {
        "model": voice_plan.get("model", config["model"]),
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": voice_plan.get("voice_id", config["voice_id"]),
            "speed": voice_plan.get("speed", config["speed"]),
            "vol": voice_plan.get("volume", config["vol"]),
            "pitch": voice_plan.get("pitch", config["pitch"]),
            "emotion": voice_plan.get("emotion", config["emotion"]),
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
        "subtitle_enable": False,
        "output_format": config["output_format"],
        "aigc_watermark": False,
        "language_boost": "Chinese",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=180)
    if response.status_code >= 400:
        raise AudioGenerationError(f"MiniMax T2A request failed: {response.status_code} {response.text}")

    data = response.json()
    if data.get("base_resp", {}).get("status_code") not in (None, 0):
        raise AudioGenerationError(f"MiniMax T2A generation failed: {data}")

    output_dir = output_dir or AUDIO_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "narration.mp3"
    result_data = data.get("data") or {}
    if config["output_format"] == "url":
        audio_url = result_data.get("audio")
        if not audio_url:
            raise AudioGenerationError(f"MiniMax T2A response missing audio url: {data}")
        audio_response = requests.get(audio_url, timeout=120)
        audio_response.raise_for_status()
        output.write_bytes(audio_response.content)
        return output

    audio_hex = result_data.get("audio")
    if not audio_hex:
        raise AudioGenerationError(f"MiniMax T2A response missing audio data: {data}")
    output.write_bytes(bytes.fromhex(audio_hex))
    return output

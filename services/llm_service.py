from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import requests


class LLMConfigError(RuntimeError):
    pass


class LLMResponseError(RuntimeError):
    pass


JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "model_config.json"


def _config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def llm_enabled() -> bool:
    env_value = os.getenv("REFLECTION_LLM_ENABLED")
    if env_value is not None:
        return env_value.lower() in {"1", "true", "yes", "on"}
    return bool(_config().get("enabled", False))


def _api_base() -> str:
    value = os.getenv("REFLECTION_LLM_API_BASE") or _config().get("api_base") or "https://api.deepseek.com"
    return value.rstrip("/")


def _api_key() -> str:
    key = os.getenv("REFLECTION_LLM_API_KEY") or _config().get("api_key", "")
    key = key.strip()
    if not key:
        raise LLMConfigError(f"Missing API key. Set api_key in {CONFIG_PATH} or REFLECTION_LLM_API_KEY.")
    return key


def _model() -> str:
    return os.getenv("REFLECTION_LLM_MODEL") or _config().get("model") or "deepseek-chat"


def _provider() -> str:
    return (os.getenv("REFLECTION_LLM_PROVIDER") or _config().get("provider") or "").lower()


def _extract_json(text: str) -> Any:
    text = THINK_RE.sub("", text).strip()
    block_match = JSON_BLOCK_RE.search(text)
    if block_match:
        text = block_match.group(1).strip()

    text = TRAILING_COMMA_RE.sub(r"\1", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start_candidates = [pos for pos in (text.find("{"), text.find("[")) if pos >= 0]
        if not start_candidates:
            raise
        start = min(start_candidates)
        end = max(text.rfind("}"), text.rfind("]"))
        if end <= start:
            raise
        sliced = TRAILING_COMMA_RE.sub(r"\1", text[start : end + 1])
        return json.loads(sliced)


def chat_json(system_prompt: str, user_prompt: str, temperature: float = 0.4) -> Any:
    base = _api_base()
    url = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
    payload = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_completion_tokens": 2048,
    }
    if _provider() != "minimax":
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=90)
    if response.status_code >= 400:
        raise LLMResponseError(f"LLM request failed: {response.status_code} {response.text}")

    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMResponseError(f"Unexpected LLM response: {data}") from exc

    try:
        return _extract_json(content)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(f"LLM did not return valid JSON: {content}") from exc

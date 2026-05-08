from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VISUAL_STYLES_PATH = ROOT / "templates" / "visual_styles.json"

RANDOM_STYLE_ID = "random"

SAFETY_RULES = {
    "visual_intent": "reflective, not depressive",
    "must": [
        "ordinary life realism",
        "visible environment detail",
        "calm self-reflection",
        "human-scale framing",
        "not too dark",
    ],
    "avoid": [
        "hopeless mood",
        "horror lighting",
        "crushed black shadows",
        "crying breakdown",
        "thriller framing",
        "commercial advertisement",
    ],
}


def load_visual_styles() -> list[dict]:
    return json.loads(VISUAL_STYLES_PATH.read_text(encoding="utf-8"))


def visual_style_choices() -> list[tuple[str, str]]:
    choices = [("随机", RANDOM_STYLE_ID)]
    choices.extend((style["label"], style["id"]) for style in load_visual_styles())
    return choices


def _seed_from_text(text: str) -> int:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _style_score(style: dict, text: str, emotion: dict) -> int:
    haystack = f"{text} {emotion.get('emotion', '')} {emotion.get('mood', '')} {emotion.get('tone', '')}"
    return sum(2 for keyword in style.get("weight_keywords", []) if keyword in haystack) + 1


def select_visual_style(style_id: str, reflection: str, emotion: dict) -> dict:
    styles = load_visual_styles()
    selected_id = style_id or RANDOM_STYLE_ID
    seed = _seed_from_text(f"{reflection}|{emotion.get('emotion', '')}")

    if selected_id != RANDOM_STYLE_ID:
        for style in styles:
            if style["id"] == selected_id:
                return {"selection": {"requested": selected_id, "resolved": style["id"], "seed": seed}, "safety_rules": SAFETY_RULES, "style": style}
        selected_id = RANDOM_STYLE_ID

    rng = random.Random(seed)
    weighted_styles = []
    for style in styles:
        weighted_styles.extend([style] * _style_score(style, reflection, emotion))
    style = rng.choice(weighted_styles or styles)
    return {"selection": {"requested": RANDOM_STYLE_ID, "resolved": style["id"], "seed": seed}, "safety_rules": SAFETY_RULES, "style": style}


def visual_style_prompt(visual_style: dict) -> str:
    style = visual_style.get("style", {})
    safety = visual_style.get("safety_rules", SAFETY_RULES)
    return "\n".join(
        [
            f"Visual intent: {safety.get('visual_intent')}",
            f"Style variant: {style.get('label')} ({style.get('id')})",
            f"Time of day: {style.get('time_of_day')}",
            f"Location family: {style.get('location_family')}",
            f"Light source: {style.get('light_source')}",
            f"Palette: {style.get('palette')}",
            f"Camera language: {style.get('camera_language')}",
            f"Scene elements to prefer: {', '.join(style.get('scene_elements', []))}",
            f"Must: {', '.join(safety.get('must', []))}",
            f"Avoid: {', '.join(safety.get('avoid', []) + style.get('avoid', []))}",
        ]
    )

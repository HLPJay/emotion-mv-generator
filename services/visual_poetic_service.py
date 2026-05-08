from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "templates" / "visual_poetic_worlds.json"
RANDOM_WORLD_ID = "random"


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"archetypes": {}, "worlds": {}}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))


def _score_item(text: str, item: dict) -> int:
    score = 0
    for keyword in item.get("keywords", []):
        if keyword and keyword in text:
            score += 3 if len(keyword) > 1 else 1
    return score


def _stable_pick(items: dict, text: str) -> tuple[str, dict]:
    keys = sorted(items)
    if not keys:
        return "", {}
    digest = hashlib.sha1(text.encode("utf-8")).digest()
    key = keys[digest[0] % len(keys)]
    return key, items[key]


def _stable_pick_scored(scored: list[tuple[str, dict, int]], text: str) -> tuple[str, dict, int]:
    if not scored:
        return "", {}, 0
    digest = hashlib.sha1(text.encode("utf-8")).digest()
    return scored[digest[0] % len(scored)]


def _select_scored(items: dict, text: str, *, best_fit_random: bool = True) -> tuple[str, dict, int]:
    scored = [(item_id, item, _score_item(text, item)) for item_id, item in items.items()]
    scored.sort(key=lambda row: (-row[2], row[0]))
    if scored and scored[0][2] > 0:
        if not best_fit_random:
            return scored[0]
        top_score = scored[0][2]
        best_candidates = [row for row in scored if row[2] == top_score]
        return _stable_pick_scored(best_candidates, text)
    picked_id, picked = _stable_pick(items, text)
    return picked_id, picked, 0


def _expression_text(expression_plan: dict | None) -> str:
    if not expression_plan:
        return ""
    parts = []
    for unit in expression_plan.get("units", []):
        parts.append(unit.get("subtitle_text", ""))
        parts.append(unit.get("spoken_text", ""))
        parts.extend(unit.get("emphasis_words", []))
    return " ".join(parts)


def _motif(archetype: dict, world: dict) -> dict:
    progression = world.get("progression", [])
    symbols = world.get("symbols", [])
    metaphor = f"{archetype.get('label', '反思')}在{world.get('label', '现实世界')}中展开：{world.get('texture', '')}"
    return {
        "visual_metaphor": metaphor,
        "recurring_symbols": symbols[:5],
        "progression": progression[:6],
        "avoid": [
            "unrelated random locations",
            "commercial poster look",
            "sci-fi robot unless the selected world requires cosmos symbolism",
            "pitch black depressed imagery",
            "text, subtitles, logos, watermarks",
            "different protagonist across shots",
        ],
    }


def build_visual_poetic_plan(
    reflection: str,
    expression_plan: dict | None = None,
    emotion: dict | None = None,
    preferred_world_id: str = "random",
) -> dict:
    config = _load_config()
    text = " ".join([reflection, _expression_text(expression_plan), json.dumps(emotion or {}, ensure_ascii=False)])
    archetype_id, archetype, archetype_score = _select_scored(config.get("archetypes", {}), text)

    worlds = config.get("worlds", {})
    if preferred_world_id != "random" and preferred_world_id in worlds:
        world_id, world, world_score = preferred_world_id, worlds[preferred_world_id], 99
        selection_mode = "manual_world_theme_archetype"
    else:
        world_id, world, world_score = _select_scored(worlds, text, best_fit_random=True)
        selection_mode = "auto_theme_best_fit"

    motif = _motif(archetype, world)
    return {
        "archetype": {
            "id": archetype_id,
            "label": archetype.get("label"),
            "core_relation": archetype.get("core_relation"),
            "emotional_motion": archetype.get("emotional_motion"),
            "match_score": archetype_score,
        },
        "world": {
            "id": world_id,
            "label": world.get("label"),
            "texture": world.get("texture"),
            "match_score": world_score,
            "selection_mode": selection_mode,
        },
        "motif": motif,
        "continuity_rules": [
            "one video must stay in one visual world",
            "repeat the same recurring symbols across shots",
            "keep the same protagonist and light logic",
            "every shot must serve the archetype relation and emotional motion",
        ],
    }


def visual_world_choices() -> list[tuple[str, str]]:
    config = _load_config()
    choices = [("自动：根据主题选择最适合", RANDOM_WORLD_ID)]
    for world_id, world in (config.get("worlds") or {}).items():
        choices.append((world.get("label", world_id), world_id))
    return choices


def visual_poetic_prompt(plan: dict | None) -> str:
    if not plan:
        return ""
    archetype = plan.get("archetype", {})
    world = plan.get("world", {})
    motif = plan.get("motif", {})
    return "\n".join(
        [
            f"Visual archetype: {archetype.get('label')} ({archetype.get('core_relation')}); {archetype.get('emotional_motion')}.",
            f"Visual world: {world.get('label')}; {world.get('texture')}.",
            f"Visual metaphor: {motif.get('visual_metaphor')}.",
            f"Recurring symbols: {', '.join(motif.get('recurring_symbols', []))}.",
            f"Progression: {' -> '.join(motif.get('progression', []))}.",
            f"Avoid: {', '.join(motif.get('avoid', []))}.",
        ]
    )

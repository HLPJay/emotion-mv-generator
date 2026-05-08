from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.expression_service import build_expression_plan
from services.subtitle_service import build_subtitle_plan_from_expression
from services.storyboard_service import build_storyboard
from services.visual_poetic_service import build_visual_poetic_plan


DEFAULT_TEXT = "向外是一种能力，需要做出自我挑战。（所以我用ai帮我跨出了这个第一步）"


def main() -> None:
    emotion = {
        "emotion": "自我挑战",
        "mood": "反思但向外",
        "tone": "克制独白",
        "visual_keywords": ["向外", "第一步", "挑战"],
    }
    expression_plan = build_expression_plan(DEFAULT_TEXT, emotion)
    visual_poetic_plan = build_visual_poetic_plan(DEFAULT_TEXT, expression_plan, emotion)
    forced_cosmos_plan = build_visual_poetic_plan(DEFAULT_TEXT, expression_plan, emotion, preferred_world_id="star_cosmos")
    subtitle_plan = build_subtitle_plan_from_expression(expression_plan)
    storyboard = build_storyboard(
        DEFAULT_TEXT,
        emotion,
        subtitle_plan["subtitles"],
        expression_plan=expression_plan,
        visual_poetic_plan=visual_poetic_plan,
    )

    print("VISUAL_POETIC_PLAN")
    print(json.dumps(visual_poetic_plan, ensure_ascii=False, indent=2))
    print("\nFORCED_STAR_COSMOS_PLAN")
    print(json.dumps(forced_cosmos_plan, ensure_ascii=False, indent=2))
    print("\nSTORYBOARD")
    print(json.dumps(storyboard, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

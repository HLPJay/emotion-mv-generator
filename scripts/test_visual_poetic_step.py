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
HABIT_TEXT = "优秀的人本身就是一种优秀，你要走向优秀，所要经历的，或许不仅仅是认知上的蜕变。（认知上发生蜕变就已经力竭了，而要对齐优秀，还需要沉淀出习惯）"
AUTO_WORLD_CASES = [
    (
        "habit_workspace",
        HABIT_TEXT,
        {"emotion": "反思", "visual_keywords": ["优秀", "认知", "习惯"]},
        "workspace_reality",
    ),
    (
        "explicit_train",
        "我坐在列车车窗边，看着站台后退，才意识到这次选择真的开始了。",
        {"emotion": "远行", "visual_keywords": ["列车", "站台", "选择"]},
        "train_journey",
    ),
    (
        "explicit_ocean",
        "我站在海边，看着潮水退去，突然明白向外并不等于逃离。",
        {"emotion": "开阔", "visual_keywords": ["海边", "潮水", "向外"]},
        "ocean_shore",
    ),
    (
        "explicit_cosmos",
        "当我用第一性原理重新看问题，眼前像是展开了一片星空宇宙。",
        {"emotion": "认知打开", "visual_keywords": ["第一性原理", "星空", "宇宙"]},
        "star_cosmos",
    ),
    (
        "explicit_rural_family",
        "我离开农村老家的院子时，父母站在门边没有多说一句。",
        {"emotion": "亲情", "visual_keywords": ["农村", "父母", "老家"]},
        "rural_family",
    ),
    (
        "explicit_city",
        "我在城市地铁口停了一会儿，终于决定去参加那场面试。",
        {"emotion": "职业转折", "visual_keywords": ["城市", "地铁", "面试"]},
        "city_daylight",
    ),
]


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
    case_results = []
    for name, text, case_emotion, expected_world_id in AUTO_WORLD_CASES:
        plan = build_visual_poetic_plan(text, None, case_emotion)
        actual_world_id = plan["world"]["id"]
        assert actual_world_id == expected_world_id, {
            "case": name,
            "expected": expected_world_id,
            "actual": actual_world_id,
            "world": plan["world"],
        }
        case_results.append({"case": name, "world": plan["world"]})
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
    print("\nAUTO_WORLD_REGRESSION")
    print(json.dumps(case_results, ensure_ascii=False, indent=2))
    print("\nSTORYBOARD")
    print(json.dumps(storyboard, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

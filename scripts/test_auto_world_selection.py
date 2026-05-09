from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.visual_poetic_service import build_visual_poetic_plan


CASES = [
    {
        "name": "habit_workspace",
        "text": "优秀的人本身就是一种优秀，你要走向优秀，所要经历的，或许不仅仅是认知上的蜕变。（认知上发生蜕变就已经力竭了，而要对齐优秀，还需要沉淀出习惯）",
        "emotion": {"emotion": "反思", "visual_keywords": ["优秀", "认知", "习惯"]},
        "expected": "workspace_reality",
    },
    {
        "name": "explicit_train",
        "text": "我坐在列车车窗边，看着站台后退，才意识到这次选择真的开始了。",
        "emotion": {"emotion": "远行", "visual_keywords": ["列车", "站台", "选择"]},
        "expected": "train_journey",
    },
    {
        "name": "explicit_ocean",
        "text": "我站在海边，看着潮水退去，突然明白向外并不等于逃离。",
        "emotion": {"emotion": "开阔", "visual_keywords": ["海边", "潮水", "向外"]},
        "expected": "ocean_shore",
    },
    {
        "name": "explicit_cosmos",
        "text": "当我用第一性原理重新看问题，眼前像是展开了一片星空宇宙。",
        "emotion": {"emotion": "认知打开", "visual_keywords": ["第一性原理", "星空", "宇宙"]},
        "expected": "star_cosmos",
    },
    {
        "name": "explicit_rural_family",
        "text": "我离开农村老家的院子时，父母站在门边没有多说一句。",
        "emotion": {"emotion": "亲情", "visual_keywords": ["农村", "父母", "老家"]},
        "expected": "rural_family",
    },
    {
        "name": "explicit_city",
        "text": "我在城市地铁口停了一会儿，终于决定去参加那场面试。",
        "emotion": {"emotion": "职业转折", "visual_keywords": ["城市", "地铁", "面试"]},
        "expected": "city_daylight",
    },
    # 隐喻场景：场景词出现在比喻句中，不加 explicit_scene_cue
    {
        "name": "metaphor_train",
        "text": "人生像一列火车，不知道开往哪里。",
        "emotion": {"emotion": "迷茫", "visual_keywords": ["人生", "方向"]},
        "expected": "train_journey",
        "expect_no_explicit": True,
        "note": "隐喻场景不加 explicit_scene_cue，但旅途/远行关键词仍匹配 train_journey",
    },
    {
        "name": "metaphor_ocean",
        "text": "世界像大海一样广阔，我想我该出发了。",
        "emotion": {"emotion": "开阔", "visual_keywords": ["世界", "出发"]},
        "expected": "ocean_shore",
        "expect_no_explicit": True,
        "note": "隐喻场景不加 explicit_scene_cue，但开阔/世界主题匹配 ocean_shore",
    },
    {
        "name": "metaphor_cosmos",
        "text": "认知像星空一样深邃，永远值得探索。",
        "emotion": {"emotion": "求知", "visual_keywords": ["认知", "探索"]},
        "expected": "star_cosmos",
        "expect_no_explicit": True,
        "note": "隐喻场景不加 explicit_scene_cue，但开阔/世界主题匹配 ocean_shore",
    },
]


def main() -> None:
    results = []
    for case in CASES:
        plan = build_visual_poetic_plan(case["text"], None, case["emotion"])
        world = plan["world"]
        ok = world["id"] == case["expected"]

        no_explicit_ok = True
        if case.get("expect_no_explicit"):
            for item in world.get("selection_debug", []):
                for r in item.get("reasons", []):
                    if "explicit_scene_cue" in r:
                        no_explicit_ok = False
                        break

        ok = ok and no_explicit_ok
        results.append(
            {
                "case": case["name"],
                "ok": ok,
                "expected": case["expected"],
                "actual": world["id"],
                "label": world.get("label"),
                "score": world.get("match_score"),
                "no_explicit_ok": no_explicit_ok if case.get("expect_no_explicit") else None,
                "selection_debug": world.get("selection_debug", [])[:3],
            }
        )

    print(json.dumps(results, ensure_ascii=False, indent=2))
    failed = [item for item in results if not item["ok"]]
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()


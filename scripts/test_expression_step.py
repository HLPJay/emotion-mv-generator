from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.audio_plan_service import build_audio_plan
from services.expression_service import build_expression_plan
from services.subtitle_service import build_subtitle_plan_from_expression


DEFAULT_TEXT = "相比于生活的困境，我一直更害怕的是怯弱的自己。（只有自己最懂自己，越害怕越回避） 你有过自己的职业规划吗？"


def main() -> None:
    emotion = {
        "emotion": "克制反思",
        "mood": "普通人自省",
        "tone": "真实独白",
        "visual_keywords": ["窗边", "笔记本", "待办"],
    }
    expression_plan = build_expression_plan(DEFAULT_TEXT, emotion)
    subtitle_plan = build_subtitle_plan_from_expression(expression_plan)
    storyboard_stub = [
        {"subtitle": subtitle, "scene": "test", "camera": "static shot", "lighting": "soft daylight", "duration": 2.0}
        for subtitle in subtitle_plan["subtitles"]
    ]
    audio_plan = build_audio_plan(subtitle_plan, emotion, storyboard_stub)

    print("EXPRESSION_PLAN")
    print(json.dumps(expression_plan, ensure_ascii=False, indent=2))
    print("\nSUBTITLE_PLAN")
    print(json.dumps(subtitle_plan, ensure_ascii=False, indent=2))
    print("\nAUDIO_NARRATION")
    print(json.dumps(audio_plan["narration"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

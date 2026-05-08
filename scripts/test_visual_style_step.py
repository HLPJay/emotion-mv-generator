from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.emotion_service import analyze_emotion
from services.storyboard_service import build_storyboard
from services.subtitle_service import build_subtitle_plan
from services.visual_style_service import RANDOM_STYLE_ID, select_visual_style, visual_style_choices


def main() -> None:
    parser = argparse.ArgumentParser(description="Test visual style selection and storyboard guidance.")
    parser.add_argument("--text", default="相比于生活的困境，我一直更害怕的是怯弱的自己。")
    parser.add_argument("--style", default=RANDOM_STYLE_ID)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        print(json.dumps(visual_style_choices(), ensure_ascii=False, indent=2))
        return

    emotion = analyze_emotion(args.text)
    visual_style = select_visual_style(args.style, args.text, emotion)
    subtitle_plan = build_subtitle_plan(args.text)
    storyboard = build_storyboard(args.text, emotion, subtitle_plan["subtitles"], visual_style)
    print(
        json.dumps(
            {
                "emotion": emotion,
                "visual_style": visual_style,
                "storyboard": storyboard,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

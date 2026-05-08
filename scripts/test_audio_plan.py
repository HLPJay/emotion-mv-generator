from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.audio_plan_service import build_audio_plan, narration_text_from_audio_plan
from services.emotion_service import analyze_emotion
from services.storyboard_service import build_storyboard
from services.subtitle_service import build_subtitle_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and inspect audio director plan.")
    parser.add_argument(
        "--text",
        default="相比于生活的困境，我一直更害怕的是怯弱的自己。",
        help="Reflection text.",
    )
    args = parser.parse_args()

    emotion = analyze_emotion(args.text)
    subtitle_plan = build_subtitle_plan(args.text)
    storyboard = build_storyboard(args.text, emotion, subtitle_plan["subtitles"])
    audio_plan = build_audio_plan(subtitle_plan, emotion, storyboard)

    print(
        json.dumps(
            {
                "subtitle_plan": subtitle_plan,
                "audio_plan": audio_plan,
                "narration_text": narration_text_from_audio_plan(audio_plan),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

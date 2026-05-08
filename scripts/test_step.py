from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.emotion_service import analyze_emotion
from services.semantic_service import expand_semantics
from services.storyboard_service import build_storyboard
from services.subtitle_service import build_subtitle_plan, build_subtitle_rhythm


def apply_rhythm_to_storyboard(storyboard: list[dict], subtitle_plan: dict) -> list[dict]:
    for shot, rhythm_item in zip(storyboard, subtitle_plan["rhythm"]):
        shot["duration"] = rhythm_item["duration"]
        shot["pause_type"] = rhythm_item["pause_type"]
    return storyboard


def dump(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Single-step tests for reflection video planning.")
    parser.add_argument(
        "step",
        choices=["semantic", "emotion", "subtitle", "subtitle_plan", "storyboard", "all"],
        help="Step to test.",
    )
    parser.add_argument(
        "--text",
        default="相比于生活的困境，我一直更害怕的是怯弱的自己。",
        help="Reflection text.",
    )
    args = parser.parse_args()

    if args.step == "semantic":
        dump(expand_semantics(args.text))
        return

    if args.step == "emotion":
        dump(analyze_emotion(args.text))
        return

    if args.step == "subtitle":
        dump(build_subtitle_rhythm(args.text))
        return

    if args.step == "subtitle_plan":
        dump(build_subtitle_plan(args.text))
        return

    emotion = analyze_emotion(args.text)
    subtitle_plan = build_subtitle_plan(args.text)
    subtitles = subtitle_plan["subtitles"]

    if args.step == "storyboard":
        dump(apply_rhythm_to_storyboard(build_storyboard(args.text, emotion, subtitles), subtitle_plan))
        return

    dump(
        {
            "semantic_expansion": expand_semantics(args.text),
            "emotion": emotion,
            "subtitle_plan": subtitle_plan,
            "storyboard": apply_rhythm_to_storyboard(build_storyboard(args.text, emotion, subtitles), subtitle_plan),
        }
    )


if __name__ == "__main__":
    main()

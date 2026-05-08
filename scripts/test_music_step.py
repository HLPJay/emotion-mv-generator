from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.audio_plan_service import build_audio_plan
from services.emotion_service import analyze_emotion
from services.music_service import generate_music_audio, music_enabled
from services.storyboard_service import build_storyboard
from services.subtitle_service import build_subtitle_plan


def main() -> None:
    text = "相比于生活的困境，我一直更害怕的是怯弱的自己。"
    emotion = analyze_emotion(text)
    subtitle_plan = build_subtitle_plan(text)
    storyboard = build_storyboard(text, emotion, subtitle_plan["subtitles"])
    audio_plan = build_audio_plan(subtitle_plan, emotion, storyboard)
    path = generate_music_audio(audio_plan)
    print(
        json.dumps(
            {
                "music_enabled": music_enabled(),
                "music_prompt": audio_plan["music"]["prompt"],
                "path": str(path) if path else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

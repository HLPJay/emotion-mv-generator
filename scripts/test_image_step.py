from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.image_service import generate_scene_images, image_model_enabled


def main() -> None:
    emotion = {
        "emotion": "长期回避",
        "mood": "深夜压抑",
        "style": {
            "palette": "low saturation blue gray",
            "texture": "film grain",
        },
    }
    storyboard = [
        {
            "scene": "深夜房间里，一个人坐在电脑前，看着未完成的待办列表，手停在键盘上很久没有动作",
            "subtitle": "相比于生活的困境。",
            "camera": "slow push",
            "lighting": "cold screen light",
            "duration": 2.2,
        }
    ]
    paths = generate_scene_images(storyboard, emotion)
    print(
        json.dumps(
            {
                "image_model_enabled": image_model_enabled(),
                "paths": [str(path) for path in paths],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

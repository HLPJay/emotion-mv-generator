from __future__ import annotations

import json
import sys
import time
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
            "scene": "深夜房间里，一个人坐在电脑前，看着未完成的待办列表",
            "subtitle": "相比于生活的困境。",
            "camera": "slow push",
            "lighting": "cold screen light",
        },
        {
            "scene": "镜子里的人影低头沉默，半张脸被冷光遮住",
            "subtitle": "我一直更害怕的。",
            "camera": "static shot",
            "lighting": "blue gray mirror reflection",
        },
        {
            "scene": "窗边空椅子和深夜城市灯光，房间安静而空旷",
            "subtitle": "是怯弱的自己。",
            "camera": "slow zoom",
            "lighting": "distant street lamp glow",
        },
    ]
    output_dir = ROOT / "generated" / "image_batch_test"
    started = time.perf_counter()
    paths = generate_scene_images(storyboard, emotion, output_dir)
    elapsed = round(time.perf_counter() - started, 2)
    print(
        json.dumps(
            {
                "image_model_enabled": image_model_enabled(),
                "elapsed_seconds": elapsed,
                "paths": [str(path) for path in paths],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

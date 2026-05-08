from pathlib import Path
from typing import Any

import gradio as gr

from services.emotion_service import analyze_emotion
from services.image_service import generate_scene_images
from services.storyboard_service import build_storyboard
from services.subtitle_service import build_subtitle_plan
from services.video_service import compose_video


ROOT = Path(__file__).parent
GENERATED_DIR = ROOT / "generated"
GENERATED_DIR.mkdir(exist_ok=True)


DEFAULT_TEXT = "相比于生活的困境，\n我一直更害怕的是怯弱的自己。"


def generate_reflection_video(reflection: str) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    reflection = reflection.strip()
    if not reflection:
        raise gr.Error("请先输入一句真实感悟。")

    emotion = analyze_emotion(reflection)
    subtitle_plan = build_subtitle_plan(reflection)
    subtitles = subtitle_plan["subtitles"]
    storyboard = build_storyboard(reflection, emotion, subtitles)
    for shot, rhythm_item in zip(storyboard, subtitle_plan["rhythm"]):
        shot["duration"] = rhythm_item["duration"]
        shot["pause_type"] = rhythm_item["pause_type"]
    image_paths = generate_scene_images(storyboard, emotion)
    video_path = compose_video(storyboard, image_paths, emotion)

    return str(video_path), emotion, storyboard


with gr.Blocks(title="AI Reflection Video Generator") as demo:
    gr.Markdown("# AI Reflection Video Generator")
    gr.Markdown("输入一句真实反思，生成一条 9:16 情绪型短视频。")

    with gr.Row():
        with gr.Column(scale=1):
            reflection_input = gr.Textbox(
                label="真实感悟",
                value=DEFAULT_TEXT,
                lines=5,
                placeholder="写下一句你真的感受到的话。",
            )
            generate_button = gr.Button("生成视频", variant="primary")

        with gr.Column(scale=1):
            video_output = gr.Video(label="生成结果")

    with gr.Row():
        emotion_output = gr.JSON(label="情绪解析")
        storyboard_output = gr.JSON(label="镜头脚本")

    generate_button.click(
        fn=generate_reflection_video,
        inputs=reflection_input,
        outputs=[video_output, emotion_output, storyboard_output],
    )


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860)

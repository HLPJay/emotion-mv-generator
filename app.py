import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import gradio as gr

from services.audio_plan_service import build_audio_plan
from services.emotion_service import analyze_emotion
from services.event_service import log_event, track_step
from services.expression_service import build_expression_plan
from services.image_service import generate_scene_images
from services.report_service import write_run_report
from services.run_service import create_run_dir, write_json, write_text
from services.storyboard_service import build_storyboard
from services.subtitle_service import build_subtitle_plan_from_expression
from services.video_service import compose_video
from services.visual_style_service import RANDOM_STYLE_ID, select_visual_style, visual_style_choices
from services.visual_continuity_service import build_visual_continuity
from services.visual_poetic_service import RANDOM_WORLD_ID, build_visual_poetic_plan, visual_world_choices


ROOT = Path(__file__).parent
GENERATED_DIR = ROOT / "generated"
GENERATED_DIR.mkdir(exist_ok=True)


DEFAULT_TEXT = "相比于生活的困境，\n我一直更害怕的是怯弱的自己。"


def generate_reflection_video(
    reflection: str,
    visual_style_id: str = RANDOM_STYLE_ID,
    visual_world_id: str = RANDOM_WORLD_ID,
) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], str]:
    reflection = reflection.strip()
    if not reflection:
        raise gr.Error("请先输入一句真实感悟。")

    run_dir = create_run_dir(reflection)
    write_text(run_dir / "input.txt", reflection)
    log_event(run_dir, "run", "started", visual_style_id=visual_style_id, visual_world_id=visual_world_id)

    with track_step(run_dir, "emotion"):
        emotion = analyze_emotion(reflection)
    write_json(run_dir / "emotion.json", emotion)
    with track_step(run_dir, "visual_style"):
        visual_style = select_visual_style(visual_style_id, reflection, emotion)
    write_json(run_dir / "visual_style.json", visual_style)
    with track_step(run_dir, "visual_continuity"):
        visual_continuity = build_visual_continuity(visual_style)
    write_json(run_dir / "visual_continuity.json", visual_continuity)
    with track_step(run_dir, "expression_plan"):
        expression_plan = build_expression_plan(reflection, emotion)
    write_json(run_dir / "expression_plan.json", expression_plan)
    with track_step(run_dir, "visual_poetic_plan"):
        visual_poetic_plan = build_visual_poetic_plan(reflection, expression_plan, emotion, visual_world_id)
    write_json(run_dir / "visual_poetic_plan.json", visual_poetic_plan)
    with track_step(run_dir, "subtitle_plan"):
        subtitle_plan = build_subtitle_plan_from_expression(expression_plan)
    write_json(run_dir / "subtitle_plan.json", subtitle_plan)
    subtitles = subtitle_plan["subtitles"]
    with track_step(run_dir, "storyboard"):
        storyboard = build_storyboard(reflection, emotion, subtitles, visual_style, visual_continuity, expression_plan, visual_poetic_plan)
    write_json(run_dir / "storyboard.json", storyboard)
    with track_step(run_dir, "audio_plan"):
        audio_plan = build_audio_plan(subtitle_plan, emotion, storyboard)
    write_json(run_dir / "audio_plan.json", audio_plan)
    adjusted_storyboard = audio_plan["adjusted_storyboard"]
    write_json(run_dir / "adjusted_storyboard.json", adjusted_storyboard)
    with track_step(run_dir, "image_generation", image_count=len(adjusted_storyboard)):
        image_paths = generate_scene_images(adjusted_storyboard, emotion, run_dir / "images", visual_style, visual_continuity, visual_poetic_plan)
    with track_step(run_dir, "video_compose"):
        video_path = compose_video(adjusted_storyboard, image_paths, emotion, audio_plan, run_dir)
    write_text(run_dir / "output_path.txt", str(video_path))
    with track_step(run_dir, "report"):
        report = write_run_report(run_dir)
    log_event(run_dir, "run", "success", final_video=str(video_path))

    return str(video_path), emotion, visual_style, expression_plan, visual_poetic_plan, subtitle_plan, audio_plan, adjusted_storyboard, report, str(run_dir)


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
            visual_style_input = gr.Dropdown(
                choices=visual_style_choices(),
                value=RANDOM_STYLE_ID,
                label="视觉风格",
            )
            visual_world_input = gr.Dropdown(
                choices=visual_world_choices(),
                value=RANDOM_WORLD_ID,
                label="意境世界",
            )
            generate_button = gr.Button("生成视频", variant="primary")

        with gr.Column(scale=1):
            video_output = gr.Video(label="生成结果")

    with gr.Tabs():
        with gr.Tab("核心"):
            with gr.Row():
                emotion_output = gr.JSON(label="情绪解析")
                visual_style_output = gr.JSON(label="视觉风格")
                visual_poetic_output = gr.JSON(label="视觉意境")
        with gr.Tab("节奏"):
            expression_plan_output = gr.JSON(label="表达导演")
            subtitle_plan_output = gr.JSON(label="字幕节奏")
            audio_plan_output = gr.JSON(label="音频计划")
        with gr.Tab("分镜"):
            storyboard_output = gr.JSON(label="镜头脚本")
        with gr.Tab("报告"):
            report_output = gr.JSON(label="运行报告")
            run_dir_output = gr.Textbox(label="归档目录")

    generate_button.click(
        fn=generate_reflection_video,
        inputs=[reflection_input, visual_style_input, visual_world_input],
        outputs=[
            video_output,
            emotion_output,
            visual_style_output,
            expression_plan_output,
            visual_poetic_output,
            subtitle_plan_output,
            audio_plan_output,
            storyboard_output,
            report_output,
            run_dir_output,
        ],
    )


if __name__ == "__main__":
    # 抑制客户端断开连接时的 asyncio 异常堆栈，只打印日志
    _original_call_connection_lost = asyncio.proactor_events._ProactorBasePipeTransport._call_connection_lost

    def _patched_call_connection_lost(self, exc):
        if isinstance(exc, ConnectionResetError):
            logging.warning("客户端连接已断开: %s", exc)
        else:
            _original_call_connection_lost(self, exc)

    _ProactorBasePipeTransport = asyncio.proactor_events._ProactorBasePipeTransport
    _ProactorBasePipeTransport._call_connection_lost = _patched_call_connection_lost

    demo.launch(server_name="127.0.0.1", server_port=7860)

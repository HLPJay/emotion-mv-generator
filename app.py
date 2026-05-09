import asyncio
import json
import logging
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Iterator

import gradio as gr

from services.audio_plan_service import build_audio_plan
from services.emotion_service import analyze_emotion
from services.event_service import log_event, track_step
from services.expression_service import build_expression_plan
from services.image_service import generate_scene_images
from services.input_structure_service import analyze_input_structure
from services.narrative_service import build_narrative_plan
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


PIPELINE_STEPS = [
    ("input_structure", "输入结构"),
    ("emotion", "情绪分析"),
    ("visual_style", "视觉风格"),
    ("visual_continuity", "视觉连续性"),
    ("expression_plan", "表达计划"),
    ("visual_poetic_plan", "意境分析"),
    ("narrative_plan", "镜头叙事"),
    ("subtitle_plan", "字幕节奏"),
    ("storyboard", "分镜脚本"),
    ("audio_plan", "音频计划"),
    ("image_generation", "图片生成"),
    ("video_compose", "视频合成"),
    ("report", "报告生成"),
]


def _initial_step_state() -> dict[str, dict[str, Any]]:
    return {
        step: {
            "label": label,
            "status": "pending",
            "duration_seconds": None,
            "message": "",
        }
        for step, label in PIPELINE_STEPS
    }


def _format_duration(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):.2f}s"
    except (TypeError, ValueError):
        return str(value)


def _status_icon(status: str) -> str:
    return {
        "pending": "WAIT",
        "running": "RUN",
        "success": "OK",
        "failed": "FAIL",
    }.get(status, "WAIT")


def _render_pipeline_status(step_state: dict[str, dict[str, Any]], run_dir: Path | None = None) -> str:
    completed = sum(1 for item in step_state.values() if item["status"] == "success")
    total = len(PIPELINE_STEPS)
    percent = int(round(completed / total * 100)) if total else 0
    filled = min(20, max(0, round(percent / 5)))
    progress_bar = "#" * filled + "-" * (20 - filled)
    running = next((item for item in step_state.values() if item["status"] == "running"), None)

    rows = [
        "| 步骤 | 状态 | 耗时 | 说明 |",
        "| --- | --- | ---: | --- |",
    ]
    for step, _label in PIPELINE_STEPS:
        item = step_state[step]
        status = item["status"]
        rows.append(
            f"| {item['label']} | {_status_icon(status)} {status} | "
            f"{_format_duration(item.get('duration_seconds'))} | {item.get('message', '')} |"
        )
    prefix = "### 生成过程\n"
    prefix += f"\n整体进度：`[{progress_bar}]` **{completed}/{total} ({percent}%)**\n"
    if running:
        detail = f"：{running.get('message')}" if running.get("message") else ""
        prefix += f"\n当前步骤：**{running['label']}**{detail}\n"
    if run_dir:
        prefix += f"\n运行目录：`{run_dir}`\n\n"
    return prefix + "\n".join(rows)


def _run_with_progress(
    call,
    on_progress,
    emit,
) -> Iterator[tuple[Any, ...]]:
    progress_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def progress_callback(event: dict[str, Any]) -> None:
        progress_queue.put(event)

    def target() -> None:
        try:
            result["value"] = call(progress_callback)
        except BaseException as exc:
            error["value"] = exc
        finally:
            progress_queue.put(None)

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    while True:
        try:
            event = progress_queue.get(timeout=0.5)
        except queue.Empty:
            yield emit()
            continue
        if event is None:
            break
        on_progress(event)
        yield emit()
    worker.join()
    if "value" in error:
        raise error["value"]
    return result.get("value")


def _read_run_events(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "run_events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def _refresh_step_state_from_events(step_state: dict[str, dict[str, Any]], run_dir: Path) -> None:
    for event in _read_run_events(run_dir):
        step = event.get("step")
        if step not in step_state:
            continue
        status = event.get("status")
        if status == "started":
            step_state[step]["status"] = "running"
        if status in {"success", "failed"}:
            step_state[step]["status"] = status
            step_state[step]["duration_seconds"] = event.get("duration_seconds")
            if status == "failed":
                step_state[step]["message"] = event.get("error", "")


def _apply_report_to_step_state(step_state: dict[str, dict[str, Any]], report: dict[str, Any]) -> None:
    for event in report.get("events", []):
        step = event.get("step")
        if step not in step_state:
            continue
        status = event.get("status")
        if status == "started":
            step_state[step]["status"] = "running"
        if status in {"success", "failed"}:
            step_state[step]["status"] = status
            step_state[step]["duration_seconds"] = event.get("duration_seconds")
            if status == "failed":
                step_state[step]["message"] = event.get("error", "")


def _render_report_summary(report: dict[str, Any] | None) -> str:
    if not report:
        return "### 报告摘要\n\n生成完成后会在这里显示关键结果。"

    warnings = report.get("warnings") or []
    warning_text = "\n".join(f"- {item}" for item in warnings) if warnings else "- 无"
    content = report.get("content_summary", {})
    audio_status = report.get("audio_status", {})
    media = report.get("media", {})
    video = media.get("video", {})
    performance = report.get("performance", {}).get("video_compose", {})
    timings = performance.get("timings") or {}
    timing_text = "\n".join(f"- {key}: {_format_duration(value)}" for key, value in timings.items()) or "- 无"
    paths = report.get("paths", {})

    return f"""### 报告摘要

**结果**
- Run ID: `{report.get('run_id')}`
- 最终视频: `{paths.get('final_video')}`
- 视频时长: {_format_duration(video.get('duration'))}
- 分辨率: {video.get('resolution')}
- 是否有音频: {video.get('has_audio')}

**内容**
- 主句主题: {content.get('main_theme')}
- 括号关系: {content.get('parenthetical_relationship')}
- 括号主题: {content.get('parenthetical_theme')}
- 情绪: {content.get('emotion')}
- 意境世界: {content.get('visual_world')}
- 叙事弧线: {content.get('narrative_arc')}
- 转折点: {content.get('narrative_turning_point')}
- 视觉风格: {content.get('visual_style')}
- 字幕数: {content.get('subtitles_count')}
- 分镜数: {content.get('adjusted_storyboard_count')}

**音频**
- BGM 存在: {audio_status.get('bgm_exists')}
- 使用 fallback ambient: {audio_status.get('used_music_fallback')}
- 环境音数量: {audio_status.get('environment_sound_count')}
- 音乐错误: {audio_status.get('music_error') or '无'}

**视频合成耗时**
{timing_text}

**风险提示**
{warning_text}
"""


def _outputs(
    video_path: str | None = None,
    input_structure: dict[str, Any] | None = None,
    emotion: dict[str, Any] | None = None,
    visual_style: dict[str, Any] | None = None,
    expression_plan: dict[str, Any] | None = None,
    visual_poetic_plan: dict[str, Any] | None = None,
    narrative_plan: dict[str, Any] | None = None,
    subtitle_plan: dict[str, Any] | None = None,
    audio_plan: dict[str, Any] | None = None,
    storyboard: list[dict[str, Any]] | None = None,
    pipeline_status: str = "",
    report_summary: str = "",
    report: dict[str, Any] | None = None,
    run_dir: str = "",
) -> tuple[Any, ...]:
    return (
        video_path,
        input_structure or {},
        emotion or {},
        visual_style or {},
        expression_plan or {},
        visual_poetic_plan or {},
        narrative_plan or {},
        subtitle_plan or {},
        audio_plan or {},
        storyboard or [],
        pipeline_status,
        report_summary,
        report or {},
        run_dir,
    )


def generate_reflection_video(
    reflection: str,
    visual_style_id: str = RANDOM_STYLE_ID,
    visual_world_id: str = RANDOM_WORLD_ID,
) -> Iterator[tuple[Any, ...]]:
    reflection = reflection.strip()
    if not reflection:
        raise gr.Error("请先输入一句真实感悟。")

    run_dir = create_run_dir(reflection)
    step_state = _initial_step_state()
    current_step = ""
    report: dict[str, Any] | None = None
    video_path: Path | None = None
    input_structure: dict[str, Any] = {}
    emotion: dict[str, Any] = {}
    visual_style: dict[str, Any] = {}
    visual_continuity: dict[str, Any] = {}
    expression_plan: dict[str, Any] = {}
    visual_poetic_plan: dict[str, Any] = {}
    narrative_plan: dict[str, Any] = {}
    subtitle_plan: dict[str, Any] = {}
    audio_plan: dict[str, Any] = {}
    adjusted_storyboard: list[dict[str, Any]] = []

    def emit() -> tuple[Any, ...]:
        return _outputs(
            str(video_path) if video_path else None,
            input_structure,
            emotion,
            visual_style,
            expression_plan,
            visual_poetic_plan,
            narrative_plan,
            subtitle_plan,
            audio_plan,
            adjusted_storyboard,
            _render_pipeline_status(step_state, run_dir),
            _render_report_summary(report),
            report,
            str(run_dir),
        )

    def start_step(step: str, message: str = "") -> None:
        nonlocal current_step
        current_step = step
        step_state[step]["status"] = "running"
        step_state[step]["message"] = message

    def update_image_progress(event: dict[str, Any]) -> None:
        completed = event.get("completed", 0)
        total = event.get("total", 0)
        index = event.get("index", "-")
        fallback = "，fallback" if event.get("fallback") else ""
        reused = "，复用上一镜头" if event.get("reused_previous") else ""
        step_state["image_generation"]["message"] = f"{completed}/{total}，scene_{int(index):02d} 完成{fallback}{reused}"

    def update_video_progress(event: dict[str, Any]) -> None:
        stage_labels = {
            "build_video_clips": "构建视频片段",
            "concatenate_video": "拼接片段",
            "music_prepare": "准备 BGM",
            "narration_prepare": "准备旁白",
            "tail_silence": "处理结尾留白",
            "background_audio": "混入背景音乐",
            "environment_audio": "混入环境音",
            "audio_mix": "合成音轨",
            "write_videofile": "编码输出 MP4",
        }
        stage = event.get("stage", "")
        label = stage_labels.get(stage, stage)
        duration = event.get("duration_seconds")
        if duration is None:
            step_state["video_compose"]["message"] = label
        else:
            step_state["video_compose"]["message"] = f"{label}完成，用时 {_format_duration(duration)}"

    write_text(run_dir / "input.txt", reflection)
    log_event(run_dir, "run", "started", visual_style_id=visual_style_id, visual_world_id=visual_world_id)
    yield emit()

    try:
        start_step("input_structure")
        yield emit()
        with track_step(run_dir, "input_structure"):
            input_structure = analyze_input_structure(reflection)
        write_json(run_dir / "input_structure.json", input_structure)
        _refresh_step_state_from_events(step_state, run_dir)

        start_step("emotion")
        yield emit()
        with track_step(run_dir, "emotion"):
            emotion = analyze_emotion(reflection, input_structure)
        write_json(run_dir / "emotion.json", emotion)
        _refresh_step_state_from_events(step_state, run_dir)

        start_step("visual_style")
        yield emit()
        with track_step(run_dir, "visual_style"):
            visual_style = select_visual_style(visual_style_id, reflection, emotion)
        write_json(run_dir / "visual_style.json", visual_style)
        _refresh_step_state_from_events(step_state, run_dir)

        start_step("visual_continuity")
        yield emit()
        with track_step(run_dir, "visual_continuity"):
            visual_continuity = build_visual_continuity(visual_style)
        write_json(run_dir / "visual_continuity.json", visual_continuity)
        _refresh_step_state_from_events(step_state, run_dir)

        start_step("expression_plan")
        yield emit()
        with track_step(run_dir, "expression_plan"):
            expression_plan = build_expression_plan(reflection, emotion, input_structure=input_structure)
        write_json(run_dir / "expression_plan.json", expression_plan)
        _refresh_step_state_from_events(step_state, run_dir)

        start_step("visual_poetic_plan")
        yield emit()
        with track_step(run_dir, "visual_poetic_plan"):
            visual_poetic_plan = build_visual_poetic_plan(reflection, expression_plan, emotion, visual_world_id, input_structure)
        write_json(run_dir / "visual_poetic_plan.json", visual_poetic_plan)
        _refresh_step_state_from_events(step_state, run_dir)

        start_step("narrative_plan")
        yield emit()
        with track_step(run_dir, "narrative_plan"):
            narrative_plan = build_narrative_plan(reflection, expression_plan, visual_poetic_plan, emotion, input_structure)
        write_json(run_dir / "narrative_plan.json", narrative_plan)
        _refresh_step_state_from_events(step_state, run_dir)

        start_step("subtitle_plan")
        yield emit()
        with track_step(run_dir, "subtitle_plan"):
            subtitle_plan = build_subtitle_plan_from_expression(expression_plan)
        write_json(run_dir / "subtitle_plan.json", subtitle_plan)
        _refresh_step_state_from_events(step_state, run_dir)

        subtitles = subtitle_plan["subtitles"]
        start_step("storyboard")
        yield emit()
        with track_step(run_dir, "storyboard"):
            storyboard = build_storyboard(
                reflection,
                emotion,
                subtitles,
                visual_style,
                visual_continuity,
                expression_plan,
                visual_poetic_plan,
                narrative_plan,
                input_structure,
            )
        write_json(run_dir / "storyboard.json", storyboard)
        _refresh_step_state_from_events(step_state, run_dir)

        start_step("audio_plan")
        yield emit()
        with track_step(run_dir, "audio_plan"):
            audio_plan = build_audio_plan(subtitle_plan, emotion, storyboard)
        write_json(run_dir / "audio_plan.json", audio_plan)
        adjusted_storyboard = audio_plan["adjusted_storyboard"]
        write_json(run_dir / "adjusted_storyboard.json", adjusted_storyboard)
        _refresh_step_state_from_events(step_state, run_dir)

        start_step("image_generation", f"{len(adjusted_storyboard)} 张")
        yield emit()
        with track_step(run_dir, "image_generation", image_count=len(adjusted_storyboard)):
            image_paths = yield from _run_with_progress(
                lambda callback: generate_scene_images(
                    adjusted_storyboard,
                    emotion,
                    run_dir / "images",
                    visual_style,
                    visual_continuity,
                    visual_poetic_plan,
                    progress_callback=callback,
                ),
                update_image_progress,
                emit,
            )
        _refresh_step_state_from_events(step_state, run_dir)

        start_step("video_compose")
        yield emit()
        with track_step(run_dir, "video_compose"):
            video_path = yield from _run_with_progress(
                lambda callback: compose_video(
                    adjusted_storyboard,
                    image_paths,
                    emotion,
                    audio_plan,
                    run_dir,
                    progress_callback=callback,
                ),
                update_video_progress,
                emit,
            )
        write_text(run_dir / "output_path.txt", str(video_path))
        _refresh_step_state_from_events(step_state, run_dir)

        start_step("report")
        yield emit()
        with track_step(run_dir, "report"):
            report = write_run_report(run_dir)
        log_event(run_dir, "run", "success", final_video=str(video_path))
        report = write_run_report(run_dir)
        _apply_report_to_step_state(step_state, report)
        yield emit()
    except Exception as exc:
        if current_step in step_state:
            step_state[current_step]["status"] = "failed"
            step_state[current_step]["message"] = str(exc)
        log_event(run_dir, "run", "failed", error_type=exc.__class__.__name__, error=str(exc))
        try:
            report = write_run_report(run_dir)
            _apply_report_to_step_state(step_state, report)
        except Exception:
            logging.exception("写入失败报告时出错")
        yield emit()
        raise gr.Error(f"生成失败：{exc}") from exc


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
            pipeline_status_output = gr.Markdown(label="生成过程")

    with gr.Tabs():
        with gr.Tab("核心"):
            with gr.Row():
                input_structure_output = gr.JSON(label="输入结构")
                emotion_output = gr.JSON(label="情绪解析")
                visual_style_output = gr.JSON(label="视觉风格")
                visual_poetic_output = gr.JSON(label="视觉意境")
                narrative_plan_output = gr.JSON(label="镜头叙事")
        with gr.Tab("节奏"):
            expression_plan_output = gr.JSON(label="表达导演")
            subtitle_plan_output = gr.JSON(label="字幕节奏")
            audio_plan_output = gr.JSON(label="音频计划")
        with gr.Tab("分镜"):
            storyboard_output = gr.JSON(label="镜头脚本")
        with gr.Tab("报告"):
            report_summary_output = gr.Markdown(label="报告摘要")
            report_output = gr.JSON(label="运行报告")
            run_dir_output = gr.Textbox(label="归档目录")

    generate_button.click(
        fn=generate_reflection_video,
        inputs=[reflection_input, visual_style_input, visual_world_input],
        outputs=[
            video_output,
            input_structure_output,
            emotion_output,
            visual_style_output,
            expression_plan_output,
            visual_poetic_output,
            narrative_plan_output,
            subtitle_plan_output,
            audio_plan_output,
            storyboard_output,
            pipeline_status_output,
            report_summary_output,
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

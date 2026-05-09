from __future__ import annotations

import math
import random
import time
import wave
import json
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont
from proglog import ProgressBarLogger

try:
    from moviepy.editor import AudioFileClip, CompositeAudioClip, CompositeVideoClip, ImageClip, concatenate_videoclips, vfx
except ImportError:
    from moviepy import AudioFileClip, CompositeAudioClip, CompositeVideoClip, ImageClip, concatenate_videoclips, vfx

from services.audio_service import generate_narration_audio, generate_narration_audio_segments
from services.music_service import generate_music_audio
from services.shared_config import get_llm_config


ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "generated" / "videos"
SUBTITLE_DIR = ROOT / "generated" / "subtitles"
MUSIC_DIR = ROOT / "assets" / "music"

VIDEO_DIR.mkdir(parents=True, exist_ok=True)
SUBTITLE_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

SIZE = (1080, 1920)
FPS = 24
VIDEO_PRESET = "veryfast"
VIDEO_THREADS = 6
SUBTITLE_STYLE = {
    "font_size": 74,
    "min_font_size": 42,
    "secondary_font_size": 50,
    "secondary_min_font_size": 34,
    "fill": (244, 244, 238, 242),
    "secondary_fill": (232, 232, 226, 220),
    "shadow": (0, 0, 0, 135),
    "position_y_ratio": 0.69,
    "secondary_position_y_ratio": 0.75,
    "max_chars_per_line": 11,
    "secondary_max_chars_per_line": 13,
    "max_lines": 2,
    "overflow_max_lines": 3,
    "max_width_ratio": 0.86,
    "vertical_margin": 64,
    "line_height_ratio": 1.34,
    "fade_in": 0.28,
    "fade_out": 0.38,
}


def _config() -> dict:
    return get_llm_config()


def _video_config() -> dict:
    video_config = _config().get("video", {})
    return {
        "fps": int(video_config.get("fps", FPS)),
        "codec": video_config.get("codec", "libx264"),
        "audio_codec": video_config.get("audio_codec", "aac"),
        "preset": video_config.get("preset", VIDEO_PRESET),
        "threads": int(video_config.get("threads", VIDEO_THREADS)),
    }


class _MoviePyProgressLogger(ProgressBarLogger):
    def __init__(
        self,
        progress_callback: Callable[[dict], None],
        *,
        stage: str,
        min_interval: float = 1.0,
    ) -> None:
        super().__init__(logged_bars=None)
        self.progress_callback = progress_callback
        self.stage = stage
        self.started = time.perf_counter()
        self.last_emit = 0.0
        self.min_interval = min_interval

    def bars_callback(self, bar, attr, value, old_value=None):
        if attr != "index":
            return

        total = self.bars.get(bar, {}).get("total")
        if not total:
            return

        now = time.perf_counter()
        if value < total and now - self.last_emit < self.min_interval:
            return
        self.last_emit = now

        elapsed = max(0.0, now - self.started)
        percent = min(100.0, max(0.0, float(value) / float(total) * 100.0))
        eta = None
        if value > 0 and value < total:
            eta = max(0.0, elapsed * (float(total) - float(value)) / float(value))

        self.progress_callback({
            "step": "video_compose",
            "stage": self.stage,
            "status": "running",
            "elapsed_seconds": round(elapsed, 3),
            "eta_seconds": round(eta, 3) if eta is not None else None,
            "percent": round(percent, 1),
            "frame_index": int(value),
            "frame_total": int(total),
        })


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        ROOT / "assets" / "fonts" / "NotoSansSC-Regular.otf",
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _subtitle_png(text: str, index: int, output_dir: Path, role: str = "primary") -> Path | None:
    if text == "...":
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    lines, font_size = _layout_subtitle_lines(text, role)
    font = _font(font_size)

    line_height = int(font_size * SUBTITLE_STYLE["line_height_ratio"])
    block_height = line_height * len(lines)
    y_ratio = SUBTITLE_STYLE["secondary_position_y_ratio"] if role == "secondary" else SUBTITLE_STYLE["position_y_ratio"]
    y = int(SIZE[1] * y_ratio) - block_height // 2
    margin = SUBTITLE_STYLE["vertical_margin"]
    y = max(margin, min(y, SIZE[1] - block_height - margin))
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (SIZE[0] - (bbox[2] - bbox[0])) // 2
        x = max(0, x)
        shadow = SUBTITLE_STYLE["shadow"]
        fill = SUBTITLE_STYLE["secondary_fill"] if role == "secondary" else SUBTITLE_STYLE["fill"]
        draw.text((x + 2, y + 2), line, fill=shadow, font=font)
        draw.text((x, y), line, fill=fill, font=font)
        y += line_height

    path = output_dir / f"subtitle_{index:02d}.png"
    image.save(path)
    return path


def _text_width(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _cjk_count(text: str) -> int:
    return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")


def _semantic_break_index(text: str) -> int:
    if len(text) < 6:
        return -1

    strong_marks = "，,。！？!?；;、 "
    soft_markers = [
        "重要的是",
        "而是",
        "但是",
        "只是",
        "所以",
        "因为",
        "如果",
        "然后",
        "以及",
        "或者",
        "并且",
        "需要",
        "还要",
        "不是",
        "就是",
        "和",
        "与",
        "但",
        "而",
        "却",
        "也",
        "还",
        "再",
        "并",
        "或",
    ]
    min_head = max(3, len(text) // 3)
    min_tail = 2
    ideal = len(text) * 0.58
    candidates: list[tuple[float, int]] = []

    for index, char in enumerate(text):
        if char in strong_marks:
            split_at = index + 1
            if split_at >= min_head and len(text) - split_at >= min_tail:
                candidates.append((abs(split_at - ideal) - 3.0, split_at))

    for marker in soft_markers:
        start = 0
        while True:
            index = text.find(marker, start)
            if index < 0:
                break
            split_at = index if marker not in {"重要的是"} else index + len(marker)
            if split_at >= min_head and len(text) - split_at >= min_tail:
                candidates.append((abs(split_at - ideal), split_at))
            start = index + len(marker)

    if not candidates:
        return -1
    return min(candidates, key=lambda item: item[0])[1]


def _wrap_text_by_width(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    preferred_cjk_chars: int,
) -> list[str]:
    lines: list[str] = []
    current = ""
    break_chars = "，,。！？!?；;、 "
    for char in text:
        candidate = current + char
        should_wrap_by_chars = _cjk_count(candidate) > preferred_cjk_chars and char not in break_chars
        if not current or (_text_width(candidate, font) <= max_width and not should_wrap_by_chars):
            current = candidate
            continue

        break_at = _semantic_break_index(current)
        if break_at > 0:
            lines.append(current[:break_at].strip())
            current = (current[break_at:] + char).strip()
        else:
            lines.append(current.strip())
            current = char.strip()

    if current:
        lines.append(current.strip())
    lines = [line for line in lines if line]

    leading_punctuation = "，,。！？!?；;、"
    fixed: list[str] = []
    punctuation_width_limit = int(SIZE[0] * 0.94)
    for line in lines:
        if fixed and line and line[0] in leading_punctuation:
            candidate = fixed[-1] + line[0]
            if _text_width(candidate, font) <= punctuation_width_limit:
                fixed[-1] = candidate
                line = line[1:].strip()
        if line:
            fixed.append(line)
    return fixed


def _wrap_subtitle_text(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    preferred_cjk_chars: int,
) -> list[str]:
    paragraphs = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    if not paragraphs:
        return []

    lines: list[str] = []
    for paragraph in paragraphs:
        lines.extend(_wrap_text_by_width(paragraph, font, max_width, preferred_cjk_chars))
    return lines


def _layout_subtitle_lines(text: str, role: str = "primary") -> tuple[list[str], int]:
    clean = text.strip()
    max_lines = SUBTITLE_STYLE["max_lines"]
    preferred_chars = SUBTITLE_STYLE["secondary_max_chars_per_line"] if role == "secondary" else SUBTITLE_STYLE["max_chars_per_line"]
    font_size = SUBTITLE_STYLE["secondary_font_size"] if role == "secondary" else SUBTITLE_STYLE["font_size"]
    min_font_size = SUBTITLE_STYLE["secondary_min_font_size"] if role == "secondary" else SUBTITLE_STYLE["min_font_size"]
    max_width = int(SIZE[0] * SUBTITLE_STYLE["max_width_ratio"])
    overflow_max_lines = SUBTITLE_STYLE["overflow_max_lines"]

    for size in range(font_size, min_font_size - 1, -2):
        font = _font(size)
        lines = _wrap_subtitle_text(clean, font, max_width, preferred_chars)
        if len(lines) <= max_lines:
            return lines, size

    for size in range(min_font_size, 23, -2):
        font = _font(size)
        lines = _wrap_subtitle_text(clean, font, max_width, preferred_chars)
        if len(lines) <= overflow_max_lines:
            return lines, size

    font = _font(24)
    lines = _wrap_subtitle_text(clean, font, max_width, preferred_chars)
    if len(lines) <= overflow_max_lines:
        return lines, 24

    kept = lines[:overflow_max_lines]
    kept[-1] = kept[-1].rstrip("。！？!?，,；;") + "..."
    while _text_width(kept[-1], font) > max_width and len(kept[-1]) > 4:
        kept[-1] = kept[-1][:-4].rstrip("。！？!?，,；;") + "..."
    return kept, 24


def _make_ambient_bgm(duration: float, emotion: dict, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or MUSIC_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    bgm_path = output_dir / "generated_ambient.wav"
    sample_rate = 44100
    mood = emotion.get("mood", "")
    base_freq = 146 if "压抑" in mood or "深夜" in mood else 174
    total_frames = int(duration * sample_rate)

    with wave.open(str(bgm_path), "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for i in range(total_frames):
            t = i / sample_rate
            envelope = min(1.0, t / 3.0, max(0.0, (duration - t) / 3.0))
            slow_pulse = 0.72 + 0.28 * math.sin(2 * math.pi * 0.055 * t)
            wave_a = math.sin(2 * math.pi * base_freq * t) * 0.56
            wave_b = math.sin(2 * math.pi * (base_freq * 1.5) * t + 0.4) * 0.22
            wave_c = math.sin(2 * math.pi * (base_freq * 2.0) * t + 1.1) * 0.08
            sample = int((wave_a + wave_b + wave_c) * slow_pulse * envelope * 2600)
            frames.extend(sample.to_bytes(2, byteorder="little", signed=True))
        wav.writeframes(bytes(frames))

    return bgm_path


def _storyboard_world_id(storyboard: list[dict]) -> str:
    for shot in storyboard:
        world_id = shot.get("visual_world_id")
        if world_id:
            return str(world_id)

    scene_text = " ".join(str(shot.get("scene", "")).lower() for shot in storyboard)
    if any(word in scene_text for word in ("ocean", "sea", "shore", "wave", "tide")):
        return "ocean_shore"
    if any(word in scene_text for word in ("mountain", "mist", "path")):
        return "mountain_path"
    if any(word in scene_text for word in ("city", "subway", "crosswalk", "street")):
        return "city_daylight"
    if any(word in scene_text for word in ("screen", "keyboard", "cursor", "draft", "publish")):
        return "workspace_reality"
    if any(word in scene_text for word in ("train", "platform", "ticket")):
        return "train_journey"
    if any(word in scene_text for word in ("star", "cosmos", "night sky")):
        return "star_cosmos"
    return "ordinary_life"


def _make_environment_sound(duration: float, storyboard: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    world_id = _storyboard_world_id(storyboard)
    path = output_dir / f"environment_{world_id}.wav"
    sample_rate = 44100
    total_frames = int(duration * sample_rate)
    rng = random.Random(f"{world_id}:{round(duration, 2)}")
    low_noise = 0.0

    def clamp_sample(value: float) -> int:
        return max(-32760, min(32760, int(value)))

    with wave.open(str(path), "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for i in range(total_frames):
            t = i / sample_rate
            fade = min(1.0, t / 1.5, max(0.0, (duration - t) / 1.5))
            noise = rng.uniform(-1.0, 1.0)
            low_noise = low_noise * 0.985 + noise * 0.015

            if world_id == "ocean_shore":
                swell = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.18 * t))
                sample = low_noise * 11500 * swell + noise * 1700 * swell
            elif world_id in {"mountain_path", "rural_family"}:
                gust = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.11 * t + 0.7))
                sample = low_noise * 7600 * gust + noise * 850 * gust
            elif world_id == "city_daylight":
                traffic_hum = math.sin(2 * math.pi * 92 * t) * 850 + math.sin(2 * math.pi * 147 * t) * 420
                sample = low_noise * 5200 + traffic_hum + noise * 450
            elif world_id == "train_journey":
                rhythm = 1.0 if int(t * 3.2) % 2 == 0 else 0.55
                sample = low_noise * 5200 + math.sin(2 * math.pi * 72 * t) * 900 * rhythm + noise * 650
            elif world_id == "star_cosmos":
                sample = low_noise * 2500 + math.sin(2 * math.pi * 110 * t) * 420 + math.sin(2 * math.pi * 220 * t) * 180
            elif world_id == "workspace_reality":
                room_tone = math.sin(2 * math.pi * 60 * t) * 520 + math.sin(2 * math.pi * 120 * t) * 180
                sample = low_noise * 3200 + room_tone + noise * 260
            else:
                room_tone = math.sin(2 * math.pi * 68 * t) * 380
                sample = low_noise * 3600 + room_tone + noise * 300

            frames.extend(clamp_sample(sample * fade).to_bytes(2, byteorder="little", signed=True))
        wav.writeframes(bytes(frames))

    return path


def _fit_audio_to_duration(clip, duration: float):
    if clip.duration < duration:
        return clip.with_duration(duration)
    return clip.subclipped(0, duration)


def _merge_windows(windows: list[tuple[float, float]], duration: float, pad: float = 0.18) -> list[tuple[float, float]]:
    normalized = []
    for start, end in windows:
        start = max(0.0, float(start) - pad)
        end = min(duration, float(end) + pad)
        if end > start:
            normalized.append((start, end))
    if not normalized:
        return []

    normalized.sort()
    merged = [normalized[0]]
    for start, end in normalized[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 0.05:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _duck_background_clip(clip, duration: float, narration_windows: list[tuple[float, float]], base_volume: float, duck_ratio: float):
    windows = _merge_windows(narration_windows, duration)
    if not windows:
        return _fit_audio_to_duration(clip, duration).with_volume_scaled(base_volume)

    segments = []
    cursor = 0.0
    duck_volume = base_volume * duck_ratio
    for start, end in windows:
        if start > cursor:
            segments.append(clip.subclipped(cursor, start).with_start(cursor).with_volume_scaled(base_volume))
        segments.append(clip.subclipped(start, end).with_start(start).with_volume_scaled(duck_volume))
        cursor = end
    if cursor < duration:
        segments.append(clip.subclipped(cursor, duration).with_start(cursor).with_volume_scaled(base_volume))
    return CompositeAudioClip(segments).with_duration(duration)


def _clip_with_motion(image_path: Path, duration: float, index: int):
    clip = ImageClip(str(image_path)).with_duration(duration).resized(height=SIZE[1])
    if clip.w < SIZE[0]:
        clip = clip.resized(width=SIZE[0])
    clip = clip.cropped(x_center=clip.w / 2, y_center=clip.h / 2, width=SIZE[0], height=SIZE[1])

    zoom_direction = 1 if index % 2 == 0 else -1

    def resize_at(t: float) -> float:
        progress = t / duration
        return 1.0 + (0.035 * progress if zoom_direction > 0 else 0.035 * (1 - progress))

    return clip.resized(resize_at).cropped(
        x_center=SIZE[0] / 2,
        y_center=SIZE[1] / 2,
        width=SIZE[0],
        height=SIZE[1],
    )


def compose_video(
    storyboard: list[dict],
    image_paths: list[Path],
    emotion: dict,
    audio_plan: dict | None = None,
    output_dir: Path | None = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> Path:
    timings: dict[str, float] = {}
    video_config = _video_config()

    def mark_timing(step: str, started: float) -> None:
        timings[step] = round(time.perf_counter() - started, 3)
        if progress_callback:
            progress_callback({"step": "video_compose", "stage": step, "duration_seconds": timings[step]})

    output_dir = output_dir or VIDEO_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    subtitle_dir = output_dir / "subtitles"
    audio_dir = output_dir / "audio"
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    if progress_callback:
        progress_callback({"step": "video_compose", "stage": "build_video_clips", "status": "running"})
    clips = []
    for index, (shot, image_path) in enumerate(zip(storyboard, image_paths), start=1):
        duration = float(shot.get("duration", 2.0))
        hold_previous = bool(shot.get("visual_hold_previous"))
        next_holds_previous = index < len(storyboard) and bool(storyboard[index].get("visual_hold_previous"))
        effects = []
        if not hold_previous:
            effects.append(vfx.FadeIn(0.35))
        if not next_holds_previous:
            effects.append(vfx.FadeOut(0.35))
        base_clip = _clip_with_motion(image_path, duration, index)
        if effects:
            base_clip = base_clip.with_effects(effects)
        subtitle_path = _subtitle_png(shot["subtitle"], index, subtitle_dir, shot.get("subtitle_role", "primary"))
        if subtitle_path:
            fade_in = min(SUBTITLE_STYLE["fade_in"], duration / 4)
            fade_out = min(SUBTITLE_STYLE["fade_out"], duration / 4)
            subtitle_clip = ImageClip(str(subtitle_path)).with_duration(duration).with_effects(
                [vfx.FadeIn(fade_in), vfx.FadeOut(fade_out)]
            )
            base_clip = CompositeVideoClip([base_clip, subtitle_clip], size=SIZE)
        clips.append(base_clip)
    mark_timing("build_video_clips", started)
    audio_clips = []
    mix_plan = (audio_plan or {}).get("mix", {})
    ambient = None
    environment = None
    music = None
    background = None
    background_source = None

    started = time.perf_counter()
    if progress_callback:
        progress_callback({"step": "video_compose", "stage": "music_prepare", "status": "running"})
    existing_music = audio_dir / "bgm.mp3"
    music_error_path = audio_dir / "music_generation_error.txt"
    try:
        music_path = existing_music if existing_music.exists() and existing_music.stat().st_size > 0 else generate_music_audio(audio_plan or {}, audio_dir)
        if music_path and music_error_path.exists():
            music_error_path.unlink()
    except Exception as exc:
        music_error_path.write_text(str(exc), encoding="utf-8")
        music_path = None
    mark_timing("music_prepare", started)

    narration = None
    narration_segments = []
    narration_windows: list[tuple[float, float]] = []
    started = time.perf_counter()
    if progress_callback:
        progress_callback({"step": "video_compose", "stage": "narration_prepare", "status": "running"})
    if audio_plan and audio_plan.get("narration"):
        try:
            narration_segments = generate_narration_audio_segments(audio_plan, audio_dir)
        except Exception:
            narration_segments = []

    # Defer concatenate until all clip-duration extensions are known.
    # Compute required base duration (sum of shot durations) first.
    base_duration = sum(float(shot.get("duration", 2.0)) for shot in storyboard)

    if narration_segments:
        narration_volume = float(mix_plan.get("narration_volume", 1.0))
        narration_clips = []
        narration_end = 0.0
        for segment in narration_segments:
            clip = (
                AudioFileClip(str(segment["path"]))
                .with_volume_scaled(narration_volume * float(segment.get("volume", 1.0)))
                .with_start(float(segment.get("start", 0.0)))
            )
            narration_end = max(narration_end, clip.start + clip.duration)
            narration_windows.append((float(clip.start), float(clip.start + clip.duration)))
            narration_clips.append(clip)
        # tail_silence also extends the last clip
        tail_silence = float((audio_plan or {}).get("tail_silence", 0.0))
        required = max(narration_end + 0.8, base_duration + tail_silence)
        extension = max(0.0, required - base_duration)
        if extension > 0:
            clips[-1] = clips[-1].with_duration(clips[-1].duration + extension)
        audio_clips.extend(narration_clips)
        narration = CompositeAudioClip(narration_clips)
    else:
        narration_source = audio_plan if isinstance(audio_plan, dict) and "narration" in audio_plan else storyboard
        try:
            narration_path = generate_narration_audio(narration_source, audio_dir)
        except Exception:
            narration_path = None
        if narration_path:
            narration_volume = float(mix_plan.get("narration_volume", 1.0))
            lead_in = float((audio_plan or {}).get("lead_in", 0.0))
            narration = AudioFileClip(str(narration_path)).with_volume_scaled(narration_volume).with_start(lead_in)
            narration_windows.append((lead_in, lead_in + narration.duration))
            tail_silence = float((audio_plan or {}).get("tail_silence", 0.0))
            required = max(lead_in + narration.duration + 0.8, base_duration + tail_silence)
            extension = max(0.0, required - base_duration)
            if extension > 0:
                clips[-1] = clips[-1].with_duration(clips[-1].duration + extension)
            audio_clips.append(narration)
        else:
            # No narration at all — still need to handle tail_silence extension
            tail_silence = float((audio_plan or {}).get("tail_silence", 0.0))
            if tail_silence > 0 and storyboard and storyboard[-1].get("subtitle") == "...":
                clips[-1] = clips[-1].with_duration(clips[-1].duration + tail_silence)
    mark_timing("narration_prepare", started)

    started = time.perf_counter()
    if progress_callback:
        progress_callback({"step": "video_compose", "stage": "concatenate_video", "status": "running"})
    video = concatenate_videoclips(clips, method="compose")
    mark_timing("concatenate_video", started)

    started = time.perf_counter()
    if progress_callback:
        progress_callback({"step": "video_compose", "stage": "background_audio", "status": "running"})
    duck_ratio = float(mix_plan.get("music_duck_ratio", 0.68))
    if music_path:
        music_volume = float(mix_plan.get("music_volume", (audio_plan or {}).get("music", {}).get("volume", 0.22)))
        background_source = _fit_audio_to_duration(AudioFileClip(str(music_path)), video.duration)
        background = _duck_background_clip(
            background_source,
            video.duration,
            narration_windows if mix_plan.get("duck_music_under_voice", True) else [],
            music_volume,
            duck_ratio,
        )
        music = background
        audio_clips.append(background)
    else:
        bgm_path = _make_ambient_bgm(video.duration, emotion, audio_dir)
        ambient_volume = float(mix_plan.get("ambient_fallback_volume", 0.18))
        background_source = _fit_audio_to_duration(AudioFileClip(str(bgm_path)), video.duration)
        background = _duck_background_clip(
            background_source,
            video.duration,
            narration_windows if mix_plan.get("duck_music_under_voice", True) else [],
            ambient_volume,
            duck_ratio,
        )
        ambient = background
        audio_clips.append(background)
    mark_timing("background_audio", started)

    started = time.perf_counter()
    if progress_callback:
        progress_callback({"step": "video_compose", "stage": "environment_audio", "status": "running"})
    if mix_plan.get("environment_sound", True):
        environment_path = _make_environment_sound(video.duration, storyboard, audio_dir)
        environment_volume = float(mix_plan.get("environment_volume", 0.14))
        environment = AudioFileClip(str(environment_path)).with_volume_scaled(environment_volume)
        audio_clips.append(environment)
    mark_timing("environment_audio", started)

    started = time.perf_counter()
    if progress_callback:
        progress_callback({"step": "video_compose", "stage": "audio_mix", "status": "running"})
    audio = CompositeAudioClip(audio_clips).with_duration(video.duration)
    video = video.with_audio(audio)
    mark_timing("audio_mix", started)

    output = output_dir / "final.mp4"
    started = time.perf_counter()
    if progress_callback:
        progress_callback({"step": "video_compose", "stage": "write_videofile", "status": "running"})
    logger = _MoviePyProgressLogger(progress_callback, stage="write_videofile") if progress_callback else None
    video.write_videofile(
        str(output),
        fps=video_config["fps"],
        codec=video_config["codec"],
        audio_codec=video_config["audio_codec"],
        preset=video_config["preset"],
        threads=video_config["threads"],
        logger=logger,
        temp_audiofile=str(output_dir / "temp_audio_for_final.m4a"),
        remove_temp=True,
    )
    mark_timing("write_videofile", started)
    (output_dir / "video_compose_timings.json").write_text(
        json.dumps(
            {
                "duration": video.duration,
                **video_config,
                "timings": timings,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    audio.close()
    if ambient:
        ambient.close()
    if environment:
        environment.close()
    if music:
        music.close()
    if background_source:
        background_source.close()
    if narration:
        narration.close()
    video.close()
    for clip in clips:
        clip.close()

    return output

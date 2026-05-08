from __future__ import annotations

import math
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    from moviepy.editor import AudioFileClip, CompositeAudioClip, CompositeVideoClip, ImageClip, concatenate_videoclips, vfx
except ImportError:
    from moviepy import AudioFileClip, CompositeAudioClip, CompositeVideoClip, ImageClip, concatenate_videoclips, vfx

from services.audio_service import generate_narration_audio, generate_narration_audio_segments
from services.music_service import generate_music_audio


ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "generated" / "videos"
SUBTITLE_DIR = ROOT / "generated" / "subtitles"
MUSIC_DIR = ROOT / "assets" / "music"

VIDEO_DIR.mkdir(parents=True, exist_ok=True)
SUBTITLE_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

SIZE = (1080, 1920)
FPS = 24
SUBTITLE_STYLE = {
    "font_size": 74,
    "min_font_size": 60,
    "secondary_font_size": 50,
    "secondary_min_font_size": 42,
    "fill": (244, 244, 238, 242),
    "secondary_fill": (232, 232, 226, 220),
    "shadow": (0, 0, 0, 135),
    "position_y_ratio": 0.69,
    "secondary_position_y_ratio": 0.75,
    "max_chars_per_line": 13,
    "secondary_max_chars_per_line": 16,
    "max_lines": 2,
    "line_height_ratio": 1.34,
    "fade_in": 0.28,
    "fade_out": 0.38,
}


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

    image = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    lines, font_size = _layout_subtitle_lines(text, role)
    font = _font(font_size)

    line_height = int(font_size * SUBTITLE_STYLE["line_height_ratio"])
    block_height = line_height * len(lines)
    y_ratio = SUBTITLE_STYLE["secondary_position_y_ratio"] if role == "secondary" else SUBTITLE_STYLE["position_y_ratio"]
    y = int(SIZE[1] * y_ratio) - block_height // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (SIZE[0] - (bbox[2] - bbox[0])) // 2
        shadow = SUBTITLE_STYLE["shadow"]
        fill = SUBTITLE_STYLE["secondary_fill"] if role == "secondary" else SUBTITLE_STYLE["fill"]
        draw.text((x + 2, y + 2), line, fill=shadow, font=font)
        draw.text((x, y), line, fill=fill, font=font)
        y += line_height

    path = output_dir / f"subtitle_{index:02d}.png"
    image.save(path)
    return path


def _layout_subtitle_lines(text: str, role: str = "primary") -> tuple[list[str], int]:
    clean = text.strip()
    max_chars = SUBTITLE_STYLE["secondary_max_chars_per_line"] if role == "secondary" else SUBTITLE_STYLE["max_chars_per_line"]
    max_lines = SUBTITLE_STYLE["max_lines"]
    font_size = SUBTITLE_STYLE["secondary_font_size"] if role == "secondary" else SUBTITLE_STYLE["font_size"]
    min_font_size = SUBTITLE_STYLE["secondary_min_font_size"] if role == "secondary" else SUBTITLE_STYLE["min_font_size"]

    if len(clean) <= max_chars:
        return [clean], font_size

    if len(clean) <= max_chars * max_lines:
        split_at = len(clean) // 2
        punctuation_points = [pos + 1 for pos, char in enumerate(clean) if char in "，,。！？!?；;"]
        if punctuation_points:
            split_at = min(punctuation_points, key=lambda pos: abs(pos - len(clean) / 2))
        return [clean[:split_at].strip(), clean[split_at:].strip()], font_size

    font_size = max(min_font_size, int(font_size * max_chars * max_lines / len(clean)))
    first = clean[:max_chars].strip()
    second = clean[max_chars : max_chars * 2 - 1].strip()
    if len(clean) > max_chars * 2 - 1:
        second = second.rstrip("。！？!?，,；;") + "..."
    return [first, second], font_size


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
            envelope = min(1.0, t / 2.0, max(0.0, (duration - t) / 2.0))
            wave_a = math.sin(2 * math.pi * base_freq * t)
            wave_b = math.sin(2 * math.pi * (base_freq * 1.5) * t) * 0.35
            sample = int((wave_a + wave_b) * envelope * 4200)
            frames.extend(sample.to_bytes(2, byteorder="little", signed=True))
        wav.writeframes(bytes(frames))

    return bgm_path


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
) -> Path:
    output_dir = output_dir or VIDEO_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    subtitle_dir = output_dir / "subtitles"
    audio_dir = output_dir / "audio"
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    clips = []
    for index, (shot, image_path) in enumerate(zip(storyboard, image_paths), start=1):
        duration = float(shot.get("duration", 2.0))
        base_clip = _clip_with_motion(image_path, duration, index).with_effects(
            [vfx.FadeIn(0.35), vfx.FadeOut(0.35)]
        )
        subtitle_path = _subtitle_png(shot["subtitle"], index, subtitle_dir, shot.get("subtitle_role", "primary"))
        if subtitle_path:
            fade_in = min(SUBTITLE_STYLE["fade_in"], duration / 4)
            fade_out = min(SUBTITLE_STYLE["fade_out"], duration / 4)
            subtitle_clip = ImageClip(str(subtitle_path)).with_duration(duration).with_effects(
                [vfx.FadeIn(fade_in), vfx.FadeOut(fade_out)]
            )
            base_clip = CompositeVideoClip([base_clip, subtitle_clip], size=SIZE)
        clips.append(base_clip)

    video = concatenate_videoclips(clips, method="compose")
    audio_clips = []
    mix_plan = (audio_plan or {}).get("mix", {})
    ambient = None
    music = None

    try:
        music_path = generate_music_audio(audio_plan or {}, audio_dir)
    except Exception:
        music_path = None

    if music_path:
        music_volume = float(mix_plan.get("music_volume", (audio_plan or {}).get("music", {}).get("volume", 0.22)))
        music = AudioFileClip(str(music_path))
        if music.duration < video.duration:
            music = music.with_duration(video.duration)
        else:
            music = music.subclipped(0, video.duration)
        audio_clips.append(music.with_volume_scaled(music_volume))
    else:
        bgm_path = _make_ambient_bgm(video.duration, emotion, audio_dir)
        ambient_volume = float(mix_plan.get("ambient_fallback_volume", 0.18))
        ambient = AudioFileClip(str(bgm_path)).with_volume_scaled(ambient_volume)
        audio_clips.append(ambient)

    narration = None
    narration_segments = []
    if audio_plan and audio_plan.get("narration"):
        try:
            narration_segments = generate_narration_audio_segments(audio_plan, audio_dir)
        except Exception:
            narration_segments = []

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
            narration_clips.append(clip)
        if narration_end + 0.4 > video.duration:
            extension = narration_end + 0.8 - video.duration
            if extension > 0 and clips:
                clips[-1] = clips[-1].with_duration(clips[-1].duration + extension)
                video.close()
                video = concatenate_videoclips(clips, method="compose")
        audio_clips.extend(narration_clips)
        narration = CompositeAudioClip(narration_clips)
    else:
        narration_path = generate_narration_audio(audio_plan or storyboard, audio_dir)
        if narration_path:
            narration_volume = float(mix_plan.get("narration_volume", 1.0))
            narration = AudioFileClip(str(narration_path)).with_volume_scaled(narration_volume)
            if narration.duration + 0.4 > video.duration:
                extension = narration.duration + 0.8 - video.duration
                if extension > 0 and clips:
                    last = clips[-1].with_duration(clips[-1].duration + extension)
                    clips[-1] = last
                    video.close()
                    video = concatenate_videoclips(clips, method="compose")
            audio_clips.append(narration)

    audio = CompositeAudioClip(audio_clips).with_duration(video.duration)
    video = video.with_audio(audio)

    output = output_dir / "final.mp4"
    video.write_videofile(
        str(output),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        logger=None,
    )
    audio.close()
    if ambient:
        ambient.close()
    if music:
        music.close()
    if narration:
        narration.close()
    video.close()
    for clip in clips:
        clip.close()

    return output

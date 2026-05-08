from __future__ import annotations

import math
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip, concatenate_videoclips, vfx
except ImportError:
    from moviepy import AudioFileClip, CompositeVideoClip, ImageClip, concatenate_videoclips, vfx


ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "generated" / "videos"
SUBTITLE_DIR = ROOT / "generated" / "subtitles"
MUSIC_DIR = ROOT / "assets" / "music"

VIDEO_DIR.mkdir(parents=True, exist_ok=True)
SUBTITLE_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

SIZE = (1080, 1920)
FPS = 24


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


def _subtitle_png(text: str, index: int) -> Path | None:
    if text == "...":
        return None

    image = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = _font(54)
    lines = []
    current = ""
    for char in text:
        current += char
        if len(current) >= 12:
            lines.append(current)
            current = ""
    if current:
        lines.append(current)

    line_height = 76
    block_height = line_height * len(lines)
    y = 1330 - block_height // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (SIZE[0] - (bbox[2] - bbox[0])) // 2
        draw.text((x + 2, y + 2), line, fill=(0, 0, 0, 128), font=font)
        draw.text((x, y), line, fill=(238, 241, 238, 245), font=font)
        y += line_height

    path = SUBTITLE_DIR / f"subtitle_{index:02d}.png"
    image.save(path)
    return path


def _make_ambient_bgm(duration: float, emotion: dict) -> Path:
    bgm_path = MUSIC_DIR / "generated_ambient.wav"
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
            sample = int((wave_a + wave_b) * envelope * 900)
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


def compose_video(storyboard: list[dict], image_paths: list[Path], emotion: dict) -> Path:
    clips = []
    for index, (shot, image_path) in enumerate(zip(storyboard, image_paths), start=1):
        duration = float(shot.get("duration", 2.0))
        base_clip = _clip_with_motion(image_path, duration, index).with_effects(
            [vfx.FadeIn(0.35), vfx.FadeOut(0.35)]
        )
        subtitle_path = _subtitle_png(shot["subtitle"], index)
        if subtitle_path:
            subtitle_clip = ImageClip(str(subtitle_path)).with_duration(duration)
            base_clip = CompositeVideoClip([base_clip, subtitle_clip], size=SIZE)
        clips.append(base_clip)

    video = concatenate_videoclips(clips, method="compose")
    bgm_path = _make_ambient_bgm(video.duration, emotion)
    audio = AudioFileClip(str(bgm_path)).with_volume_scaled(0.55)
    video = video.with_audio(audio)

    output = VIDEO_DIR / "final.mp4"
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
    video.close()
    for clip in clips:
        clip.close()

    return output

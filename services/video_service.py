from __future__ import annotations

import math
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    from moviepy.editor import AudioFileClip, CompositeAudioClip, CompositeVideoClip, ImageClip, concatenate_videoclips, vfx
except ImportError:
    from moviepy import AudioFileClip, CompositeAudioClip, CompositeVideoClip, ImageClip, concatenate_videoclips, vfx

from services.audio_service import generate_narration_audio
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


def _subtitle_png(text: str, index: int, output_dir: Path) -> Path | None:
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

    path = output_dir / f"subtitle_{index:02d}.png"
    image.save(path)
    return path


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
        subtitle_path = _subtitle_png(shot["subtitle"], index, subtitle_dir)
        if subtitle_path:
            subtitle_clip = ImageClip(str(subtitle_path)).with_duration(duration)
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

    narration_path = generate_narration_audio(audio_plan or storyboard, audio_dir)
    narration = None
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

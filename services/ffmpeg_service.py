from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any


def ffmpeg_available() -> bool:
    """Check if ffmpeg is available in PATH."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _probe_duration(path: Path) -> float | None:
    """Get duration of a media file using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def replace_video_audio(
    input_video: Path,
    output_video: Path,
    audio_tracks: list[dict],
    duration: float | None = None,
) -> dict[str, Any]:
    """Replace or mix audio tracks in a video using FFmpeg without re-encoding video.

    Args:
        input_video: Path to the input video file.
        output_video: Path to the output video file.
        audio_tracks: List of audio track dicts, each with:
            - path: Path to audio file
            - start: float, start time in seconds (0 for BGM)
            - volume: float, volume multiplier (1.0 = no change)
        duration: Optional target duration. Not used for audio timing.

    Returns:
        Dict with success status, engine, mode, and other metadata.
    """
    input_video = Path(input_video)
    output_video = Path(output_video)

    if not ffmpeg_available():
        return {
            "success": False,
            "engine": "ffmpeg",
            "mode": "audio_only",
            "error": "FFmpeg is not available",
            "error_type": "FFmpegNotAvailable",
        }

    if not input_video.exists():
        return {
            "success": False,
            "engine": "ffmpeg",
            "mode": "audio_only",
            "error": f"Input video does not exist: {input_video}",
            "error_type": "FileNotFoundError",
        }

    if not audio_tracks:
        return {
            "success": False,
            "engine": "ffmpeg",
            "mode": "audio_only",
            "error": "No audio tracks provided",
            "error_type": "ValueError",
        }

    for track in audio_tracks:
        if not track["path"].exists():
            return {
                "success": False,
                "engine": "ffmpeg",
                "mode": "audio_only",
                "error": f"Audio file does not exist: {track['path']}",
                "error_type": "FileNotFoundError",
            }

    # Probe video duration from input if not provided
    video_duration = duration or _probe_duration(input_video)
    if not video_duration:
        return {
            "success": False,
            "engine": "ffmpeg",
            "mode": "audio_only",
            "error": f"Could not determine video duration from {input_video}",
            "error_type": "ValueError",
        }

    tmp_output = output_video.parent / "final_recompose_tmp.mp4"
    started = time.perf_counter()
    cmd = ["ffmpeg", "-y", "-hide_banner"]

    # Input video
    cmd += ["-i", str(input_video)]

    # Input audio files
    for track in audio_tracks:
        cmd += ["-i", str(track["path"])]

    # Build filter complex
    if len(audio_tracks) == 1:
        # Single audio: replace the audio track, trimmed to video duration
        filter_complex = "[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
        if audio_tracks[0].get("volume", 1.0) != 1.0:
            vol = audio_tracks[0]["volume"]
            filter_complex += f",volume={vol}"
        # Trim to video duration so audio doesn't extend past video
        filter_complex += f",atrim=0:{video_duration},asetpts=PTS-STARTPTS[aout]"
        cmd += ["-filter_complex", filter_complex]
        cmd += ["-map", "0:v:0", "-map", "[aout]"]
    else:
        # Multiple audio: each track gets aformat, optional adelay, optional volume
        # All trimmed to video duration, then amix with duration=first
        # Track labels: [1:a], [2:a], ... [N:a]
        # Output labels: [bgm], [tr1], [tr2], ...
        filter_parts = []
        for i, track in enumerate(audio_tracks, start=1):
            label = f"[{i}:a]"
            aformat = f"{label}aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
            start_ms = int(track.get("start", 0) * 1000)
            vol = track.get("volume", 1.0)
            if start_ms > 0:
                # adelay takes delay in ms, repeated for each channel (stereo = 2 channels)
                aformat += f",adelay={start_ms}|{start_ms}"
            if vol != 1.0:
                aformat += f",volume={vol}"
            # Trim to video duration so no audio extends past video end
            aformat += f",atrim=0:{video_duration},asetpts=PTS-STARTPTS"
            out_label = "[bgm]" if i == 1 else f"[tr{i-1}]"
            filter_parts.append(aformat + out_label)

        filter_complex = ";".join(filter_parts) + ";"
        # Mix all tracks: duration=first uses the first input's duration
        mix_inputs = "".join(
            "[bgm]" if i == 0 else f"[tr{i}]"
            for i in range(len(audio_tracks))
        )
        # After amix, trim once more to exact video duration
        filter_complex += f"{mix_inputs}amix=inputs={len(audio_tracks)}:duration=first:normalize=0,atrim=0:{video_duration},asetpts=PTS-STARTPTS[aout]"

        cmd += ["-filter_complex", filter_complex]
        cmd += ["-map", "0:v:0", "-map", "[aout]"]

    # Video stream: copy without re-encoding
    cmd += ["-c:v", "copy"]
    # Audio stream: encode as AAC
    cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-map_metadata", "-1"]
    # Stop encoding when the shortest stream (video) ends
    cmd += ["-shortest"]
    cmd += ["-progress", "pipe:1", str(tmp_output)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown FFmpeg error"
            if tmp_output.exists():
                tmp_output.unlink()
            return {
                "success": False,
                "engine": "ffmpeg",
                "mode": "audio_only",
                "error": f"FFmpeg failed with code {result.returncode}: {error_msg}",
                "error_type": "FFmpegError",
                "command": " ".join(str(c) for c in cmd),
            }

        if not tmp_output.exists():
            return {
                "success": False,
                "engine": "ffmpeg",
                "mode": "audio_only",
                "error": "FFmpeg completed but output file was not created",
                "error_type": "FFmpegError",
                "command": " ".join(str(c) for c in cmd),
            }

        # Verify tmp file is not empty
        if tmp_output.stat().st_size == 0:
            tmp_output.unlink()
            return {
                "success": False,
                "engine": "ffmpeg",
                "mode": "audio_only",
                "error": "FFmpeg created empty output file",
                "error_type": "FFmpegError",
                "command": " ".join(str(c) for c in cmd),
            }

        # Atomically replace original with tmp file
        tmp_output.replace(output_video)

        output_duration = _probe_duration(output_video)
        elapsed_seconds = round(time.perf_counter() - started, 3)

        return {
            "success": True,
            "engine": "ffmpeg",
            "mode": "audio_only",
            "video_stream_copied": True,
            "output_path": str(output_video),
            "input_video_duration_seconds": video_duration,
            "elapsed_seconds": elapsed_seconds,
            "output_duration_seconds": output_duration,
            "command": " ".join(str(c) for c in cmd),
            "warnings": [],
        }

    except Exception as exc:
        if tmp_output.exists():
            tmp_output.unlink()
        return {
            "success": False,
            "engine": "ffmpeg",
            "mode": "audio_only",
            "error": str(exc),
            "error_type": exc.__class__.__name__,
            "command": " ".join(str(c) for c in cmd) if 'cmd' in locals() else "",
        }
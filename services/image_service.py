from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import shutil
import textwrap
from pathlib import Path
import time
from typing import Callable

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "generated" / "images"
CONFIG_PATH = ROOT / "config" / "model_config.json"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

SIZE = (1080, 1920)
MAX_IMAGE_PROMPT_CHARS = 1400


class ImageGenerationError(RuntimeError):
    pass


def _config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def _image_config() -> dict:
    config = _config()
    image_config = config.get("image", {})
    return {
        "enabled": bool(image_config.get("enabled", False)),
        "provider": image_config.get("provider", config.get("provider", "minimax")),
        "api_base": image_config.get("api_base", config.get("api_base", "https://api.minimaxi.com/v1")),
        "model": image_config.get("model", "image-01"),
        "api_key": image_config.get("api_key") or config.get("api_key", ""),
        "aspect_ratio": image_config.get("aspect_ratio", "9:16"),
        "response_format": image_config.get("response_format", "base64"),
        "prompt_optimizer": bool(image_config.get("prompt_optimizer", True)),
        "fallback_on_error": bool(image_config.get("fallback_on_error", True)),
        "max_workers": int(image_config.get("max_workers", 3)),
        "max_retries": int(image_config.get("max_retries", 2)),
    }


def image_model_enabled() -> bool:
    return bool(_image_config()["enabled"])


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


def _seed_color(text: str) -> tuple[int, int, int]:
    digest = hashlib.sha1(text.encode("utf-8")).digest()
    return 20 + digest[0] % 30, 28 + digest[1] % 34, 38 + digest[2] % 42


def _draw_grain(image: Image.Image, seed_text: str) -> Image.Image:
    digest = hashlib.sha1(seed_text.encode("utf-8")).digest()
    grain = Image.effect_noise(SIZE, 18 + digest[0] % 20).convert("L")
    grain = Image.merge("RGB", (grain, grain, grain)).point(lambda p: int(p * 0.18))
    return Image.blend(image, grain, 0.16)


def _draw_scene_card(draw: ImageDraw.ImageDraw, scene: str) -> None:
    title_font = _font(44)
    body_font = _font(32)
    wrapped = textwrap.wrap(scene, width=18)
    y = 1210
    draw.text((92, y), "CINEMATIC LIFE SHOT", fill=(142, 158, 168), font=body_font)
    y += 72
    for line in wrapped[:4]:
        draw.text((92, y), line, fill=(218, 225, 226), font=title_font)
        y += 62


def _build_image_prompt(
    shot: dict,
    emotion: dict,
    visual_style: dict | None = None,
    visual_continuity: dict | None = None,
    visual_poetic_plan: dict | None = None,
) -> str:
    style = emotion.get("style", {})
    style_data = (visual_style or {}).get("style", {})
    continuity = visual_continuity or {}
    subject = continuity.get("subject", {})
    location = continuity.get("location", {})
    lighting = continuity.get("lighting", {})
    palette = continuity.get("palette", {})
    recurring = ", ".join(location.get("recurring_objects", [])[:4])
    poetic = visual_poetic_plan or {}
    poetic_world = poetic.get("world", {})
    poetic_archetype = poetic.get("archetype", {})
    motif = poetic.get("motif", {})
    motif_symbols = ", ".join((motif.get("recurring_symbols") or shot.get("recurring_symbols") or [])[:5])
    motif_progression = " -> ".join((motif.get("progression") or [])[:5])
    narrative_function = shot.get("narrative_function", "")
    emotional_purpose = shot.get("emotional_purpose", "")
    visual_intent = shot.get("visual_intent", "")
    parenthetical_relationship = shot.get("parenthetical_relationship", "")
    parenthetical_theme = shot.get("parenthetical_theme", "")
    question_strategy = shot.get("question_strategy", "")

    prompt = "\n".join(
        [
            "Realistic cinematic vertical photo, 9:16.",
            "Reflective, not depressive. Calm self-reflection, ordinary life realism, visible details, not too dark.",
            "This frame must serve a narrative function, not just illustrate keywords.",
            f"Narrative function: {narrative_function}.",
            f"Emotional purpose: {emotional_purpose}.",
            f"Visual intent: {visual_intent}.",
            f"Parenthetical layer relationship: {parenthetical_relationship}. Parenthetical theme: {parenthetical_theme}.",
            f"Question or rhetorical strategy: {question_strategy}.",
            "If this frame belongs to the parenthetical layer, keep the same visual world but show the second-layer meaning; do not merely repeat the main pressure image.",
            f"One-video visual world: {poetic_world.get('label', shot.get('visual_world', 'ordinary reflective world'))}; {poetic_world.get('texture', '')}.",
            f"Visual archetype: {poetic_archetype.get('label', '')}; relation: {poetic_archetype.get('core_relation', '')}; motion: {poetic_archetype.get('emotional_motion', '')}.",
            f"Shared motif symbols in this shot: {motif_symbols}. Progression: {motif_progression}.",
            f"Scene: {_limit_text(shot['scene'], 360)}",
            f"Image style: {style_data.get('label', 'quiet reflective realism')}; lighting: {style_data.get('lighting_style', '')}; palette: {style_data.get('color_palette', '')}; texture: {style_data.get('texture', '')}.",
            f"Same subject: {subject.get('identity', 'same ordinary adult')}, {subject.get('appearance', 'simple everyday clothing')}.",
            f"Continuity: same visual world, recurring objects: {recurring}.",
            f"Lighting: {lighting.get('main_source', shot.get('lighting', 'soft available light'))}; {lighting.get('brightness', 'gentle contrast')}.",
            f"Palette: {palette.get('base', style.get('palette', 'low saturation neutral tones'))}. Texture: {style.get('texture', 'subtle film grain')}.",
            f"Camera: {shot.get('camera', 'slow push')}. Emotion: {emotion.get('emotion', 'subtle introspection')}.",
            "Avoid: text, subtitles, logo, watermark, poster design, horror, pitch black, crying, glossy commercial, sci-fi, fantasy.",
        ]
    )
    return _limit_text(prompt, MAX_IMAGE_PROMPT_CHARS)


def _limit_text(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _resize_and_save(image: Image.Image, path: Path) -> Path:
    image = image.convert("RGB")
    image = ImageOps.fit(image, SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    image.save(path)
    return path


def _is_retryable_image_error(exc: Exception) -> bool:
    msg = str(exc)
    if "status_code" in msg and "1033" in msg:
        return True
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True
    return False


def _generate_minimax_image(
    shot: dict,
    emotion: dict,
    index: int,
    output_dir: Path,
    visual_style: dict | None = None,
    visual_continuity: dict | None = None,
    visual_poetic_plan: dict | None = None,
) -> Path:
    config = _image_config()
    api_key = config["api_key"].strip()
    if not api_key:
        raise ImageGenerationError("Missing image API key. Set image.api_key or top-level api_key in config/model_config.json.")

    api_base = config["api_base"].rstrip("/")
    url = f"{api_base}/image_generation" if api_base.endswith("/v1") else f"{api_base}/v1/image_generation"
    payload = {
        "model": config["model"],
        "prompt": _build_image_prompt(shot, emotion, visual_style, visual_continuity, visual_poetic_plan),
        "aspect_ratio": config["aspect_ratio"],
        "response_format": config["response_format"],
        "n": 1,
        "prompt_optimizer": config["prompt_optimizer"],
        "aigc_watermark": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    output = output_dir / f"scene_{index:02d}.png"
    max_retries = config.get("max_retries", 2)
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=180)
            if response.status_code >= 400:
                raise ImageGenerationError(f"MiniMax image request failed: {response.status_code} {response.text}")

            data = response.json()
            base_resp = data.get("base_resp", {})
            status_code = base_resp.get("status_code")
            if status_code not in (None, 0):
                exc = ImageGenerationError(f"MiniMax image generation failed: {data}")
                if attempt < max_retries and _is_retryable_image_error(exc):
                    time.sleep(2 ** attempt)
                    continue
                raise exc

            image_data = data.get("data", {})
            if config["response_format"] == "base64":
                images = image_data.get("image_base64") or image_data.get("images") or []
                if not images:
                    raise ImageGenerationError(f"MiniMax image response missing base64 data: {data}")
                image_bytes = base64.b64decode(images[0])
                from io import BytesIO

                image = Image.open(BytesIO(image_bytes))
                return _resize_and_save(image, output)

            image_urls = image_data.get("image_urls") or []
            if not image_urls:
                raise ImageGenerationError(f"MiniMax image response missing image url: {data}")
            image_response = requests.get(image_urls[0], timeout=120)
            image_response.raise_for_status()
            from io import BytesIO

            image = Image.open(BytesIO(image_response.content))
            return _resize_and_save(image, output)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries and _is_retryable_image_error(exc):
                time.sleep(2 ** attempt)
                continue
            raise exc
    raise last_exc or ImageGenerationError("Unexpected retry loop exit")


def _generate_placeholder_image(shot: dict, emotion: dict, index: int, output_dir: Path) -> Path:
    base_mood = emotion.get("mood", "night")
    scene = shot["scene"]
    base = _seed_color(scene + base_mood)
    image = Image.new("RGB", SIZE, base)
    overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for step in range(0, SIZE[1], 8):
        alpha = int(115 * (step / SIZE[1]))
        draw.rectangle((0, step, SIZE[0], step + 8), fill=(12, 18, 26, alpha))

    draw.ellipse((-280, 220, 780, 1420), fill=(46, 72, 92, 52))
    draw.rectangle((120, 480, 960, 1120), fill=(12, 18, 24, 125))
    draw.rectangle((170, 550, 910, 980), fill=(58, 82, 96, 95))
    draw.rectangle((190, 575, 890, 955), outline=(132, 154, 166, 90), width=3)
    draw.rectangle((280, 1030, 820, 1075), fill=(24, 27, 31, 170))
    draw.rectangle((380, 1090, 720, 1125), fill=(16, 18, 22, 180))

    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    image = image.filter(ImageFilter.GaussianBlur(radius=0.45))
    image = _draw_grain(image, scene)

    draw = ImageDraw.Draw(image)
    _draw_scene_card(draw, scene)
    draw.text((92, 1560), shot["lighting"], fill=(126, 142, 153), font=_font(30))

    path = output_dir / f"scene_{index:02d}.png"
    image.save(path)
    return path


def generate_scene_images(
    storyboard: list[dict],
    emotion: dict,
    output_dir: str | Path | None = None,
    visual_style: dict | None = None,
    visual_continuity: dict | None = None,
    visual_poetic_plan: dict | None = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> list[Path]:
    config = _image_config()
    output_dir = Path(output_dir) if output_dir is not None else IMAGE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_image in output_dir.glob("scene_*.png"):
        old_image.unlink()

    def generate_one(index: int, shot: dict) -> Path:
        if config["enabled"]:
            try:
                return _generate_minimax_image(shot, emotion, index, output_dir, visual_style, visual_continuity, visual_poetic_plan)
            except Exception as exc:
                errors[index] = str(exc)
                if not config["fallback_on_error"]:
                    raise
                return _generate_placeholder_image(shot, emotion, index, output_dir)
        return _generate_placeholder_image(shot, emotion, index, output_dir)

    indexed_shots = list(enumerate(storyboard, start=1))
    generative_shots = [(index, shot) for index, shot in indexed_shots if not shot.get("visual_hold_previous")]
    max_workers = max(1, min(config["max_workers"], len(generative_shots) or 1))
    results: dict[int, Path] = {}
    errors: dict[int, str] = {}
    reused_indices: list[int] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(generate_one, index, shot): index for index, shot in generative_shots}
        completed = 0
        for future in as_completed(futures):
            index = futures[future]
            results[index] = future.result()
            completed += 1
            if progress_callback:
                progress_callback(
                    {
                        "step": "image_generation",
                        "completed": completed,
                        "total": len(indexed_shots),
                        "index": index,
                        "path": str(results[index]),
                        "fallback": index in errors or not config["enabled"],
                    }
                )

    completed = len(generative_shots)
    for index, shot in indexed_shots:
        if not shot.get("visual_hold_previous"):
            continue

        previous_path = results.get(index - 1)
        if previous_path and previous_path.exists():
            reused_path = output_dir / f"scene_{index:02d}.png"
            shutil.copyfile(previous_path, reused_path)
            results[index] = reused_path
            reused_indices.append(index)
        else:
            results[index] = generate_one(index, shot)

        completed += 1
        if progress_callback:
            progress_callback(
                {
                    "step": "image_generation",
                    "completed": completed,
                    "total": len(indexed_shots),
                    "index": index,
                    "path": str(results[index]),
                    "fallback": index in errors or not config["enabled"],
                    "reused_previous": index in reused_indices,
                }
            )

    paths = [results[index] for index, _ in indexed_shots]
    metadata = {
        "enabled": config["enabled"],
        "model": config["model"],
        "max_prompt_chars": MAX_IMAGE_PROMPT_CHARS,
        "max_workers": max_workers,
        "generated_count": len(generative_shots),
        "visual_hold_reused_indices": reused_indices,
        "paths": [str(path) for path in paths],
        "fallback_detected": bool(errors) or not config["enabled"],
        "fallback_indices": sorted(errors),
        "note": "placeholder fallback images are usually generated in seconds and may contain CINEMATIC LIFE SHOT text",
        "errors": errors,
    }
    (output_dir / "image_generation_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths

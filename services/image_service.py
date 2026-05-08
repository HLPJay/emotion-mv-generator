from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import textwrap
from pathlib import Path

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
) -> str:
    style = emotion.get("style", {})
    style_data = (visual_style or {}).get("style", {})
    continuity = visual_continuity or {}
    subject = continuity.get("subject", {})
    location = continuity.get("location", {})
    lighting = continuity.get("lighting", {})
    palette = continuity.get("palette", {})
    recurring = ", ".join(location.get("recurring_objects", [])[:4])

    prompt = "\n".join(
        [
            "Realistic cinematic vertical photo, 9:16.",
            "Reflective, not depressive. Calm self-reflection, ordinary life realism, visible details, not too dark.",
            f"Scene: {_limit_text(shot['scene'], 360)}",
            f"Style: {style_data.get('label', 'quiet reflective realism')}; {style_data.get('time_of_day', '')}; {style_data.get('location_family', '')}.",
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


def _generate_minimax_image(
    shot: dict,
    emotion: dict,
    index: int,
    output_dir: Path,
    visual_style: dict | None = None,
    visual_continuity: dict | None = None,
) -> Path:
    config = _image_config()
    api_key = config["api_key"].strip()
    if not api_key:
        raise ImageGenerationError("Missing image API key. Set image.api_key or top-level api_key in config/model_config.json.")

    api_base = config["api_base"].rstrip("/")
    url = f"{api_base}/image_generation" if api_base.endswith("/v1") else f"{api_base}/v1/image_generation"
    payload = {
        "model": config["model"],
        "prompt": _build_image_prompt(shot, emotion, visual_style, visual_continuity),
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
    response = requests.post(url, headers=headers, json=payload, timeout=180)
    if response.status_code >= 400:
        raise ImageGenerationError(f"MiniMax image request failed: {response.status_code} {response.text}")

    data = response.json()
    if data.get("base_resp", {}).get("status_code") not in (None, 0):
        raise ImageGenerationError(f"MiniMax image generation failed: {data}")

    output = output_dir / f"scene_{index:02d}.png"
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
) -> list[Path]:
    config = _image_config()
    output_dir = Path(output_dir) if output_dir is not None else IMAGE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_image in output_dir.glob("scene_*.png"):
        old_image.unlink()

    def generate_one(index: int, shot: dict) -> Path:
        if config["enabled"]:
            try:
                return _generate_minimax_image(shot, emotion, index, output_dir, visual_style, visual_continuity)
            except Exception as exc:
                errors[index] = str(exc)
                if not config["fallback_on_error"]:
                    raise
                return _generate_placeholder_image(shot, emotion, index, output_dir)
        return _generate_placeholder_image(shot, emotion, index, output_dir)

    indexed_shots = list(enumerate(storyboard, start=1))
    max_workers = max(1, min(config["max_workers"], len(indexed_shots) or 1))
    results: dict[int, Path] = {}
    errors: dict[int, str] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(generate_one, index, shot): index for index, shot in indexed_shots}
        for future in as_completed(futures):
            index = futures[future]
            results[index] = future.result()

    paths = [results[index] for index, _ in indexed_shots]
    metadata = {
        "enabled": config["enabled"],
        "model": config["model"],
        "max_prompt_chars": MAX_IMAGE_PROMPT_CHARS,
        "max_workers": max_workers,
        "paths": [str(path) for path in paths],
        "fallback_detected": bool(errors) or not config["enabled"],
        "fallback_indices": sorted(errors),
        "note": "placeholder fallback images are usually generated in seconds and may contain CINEMATIC LIFE SHOT text",
        "errors": errors,
    }
    (output_dir / "image_generation_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths

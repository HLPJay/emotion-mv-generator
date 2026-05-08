from __future__ import annotations


def build_visual_continuity(visual_style: dict) -> dict:
    style = visual_style.get("style", {})
    elements = style.get("scene_elements", [])
    recurring_objects = elements[:4] if elements else ["window", "desk", "cup", "notebook"]

    return {
        "subject": {
            "identity": "same ordinary adult throughout the video",
            "age_range": "late 20s to late 30s",
            "appearance": "natural face, simple everyday clothing, restrained expression",
            "expression": "calm self-reflection, no crying, no dramatic pain",
        },
        "location": {
            "primary_space": style.get("location_family", "ordinary lived-in space"),
            "recurring_objects": recurring_objects,
            "spatial_rules": [
                "all shots should feel like the same visual world",
                "use different angles within the same location family",
                "reuse recurring objects as visual anchors",
                "avoid sudden jumps to unrelated locations",
            ],
        },
        "lighting": {
            "main_source": style.get("light_source", "soft available light"),
            "brightness": "visible details, gentle contrast, no crushed black",
        },
        "palette": {
            "base": style.get("palette", "low saturation neutral tones"),
            "rule": "keep color and contrast consistent across all shots",
        },
    }


def visual_continuity_prompt(visual_continuity: dict | None) -> str:
    if not visual_continuity:
        return "Keep subject, location family, lighting and palette consistent across shots."

    subject = visual_continuity.get("subject", {})
    location = visual_continuity.get("location", {})
    lighting = visual_continuity.get("lighting", {})
    palette = visual_continuity.get("palette", {})
    return "\n".join(
        [
            "Visual continuity for this single video:",
            f"Subject: {subject.get('identity')}, {subject.get('age_range')}, {subject.get('appearance')}",
            f"Expression: {subject.get('expression')}",
            f"Primary space: {location.get('primary_space')}",
            f"Recurring objects: {', '.join(location.get('recurring_objects', []))}",
            f"Spatial rules: {', '.join(location.get('spatial_rules', []))}",
            f"Lighting: {lighting.get('main_source')}; {lighting.get('brightness')}",
            f"Palette: {palette.get('base')}; {palette.get('rule')}",
        ]
    )

from __future__ import annotations

import re


# Normalise whitespace: collapse runs of whitespace, strip leading/trailing.
def normalize(text: str) -> str:
    return " ".join((text or "").split()).strip()


# Ensure text ends with the given punctuation character; returns empty string if text is blank.
def ensure_punctuation(text: str, punctuation: str = "。") -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    if cleaned[-1] in "。！？!?；;，,":
        return cleaned
    return cleaned + punctuation


# Strip trailing punctuation then append "。" — useful for rebuilding sentences from fragments.
def ensure_sentence(text: str) -> str:
    cleaned = re.sub(r"[。！？!?；;，,.\s]+$", "", (text or "").strip())
    if not cleaned:
        return ""
    return cleaned + "。"

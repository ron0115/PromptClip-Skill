from __future__ import annotations


VALID_MODES = {"auto", "fast", "precise"}

_PRECISION_TERMS = (
    "精剪",
    "精细剪辑",
    "精准剪辑",
    "精准切点",
    "精确切点",
    "精准边界",
    "精确剪辑",
    "逐帧",
    "每一帧",
    "每帧",
    "严格符合",
    "最终版",
    "frame-by-frame",
    "frame by frame",
    "frame accurate",
    "precise edit",
    "exact cut",
)


def resolve_mode(prompt: str, requested: str | None = None) -> str:
    mode = requested or "auto"
    if mode not in VALID_MODES:
        raise ValueError("Mode must be auto, fast, or precise")
    if mode != "auto":
        return mode

    normalized_prompt = prompt.strip().lower()
    if any(term in normalized_prompt for term in _PRECISION_TERMS):
        return "precise"
    return "fast"

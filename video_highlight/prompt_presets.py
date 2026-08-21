from __future__ import annotations

import os
from typing import Any


PROMPT_PRESETS: list[dict[str, Any]] = [
    {
        "preset_id": "leading-obstruction-trim",
        "enabled": True,
        "description": "Avoid segments whose opening is visibly obstructed.",
        "prompt": (
            "When a candidate clip starts with an obvious obstruction, treat that opening as unusable. "
            "Prefer the first clearly visible moment instead of keeping a blocked lead-in."
        ),
    }
]


def enabled_prompt_preset_ids() -> set[str]:
    disabled = {
        preset_id.strip()
        for preset_id in os.environ.get("PROMPTCLIP_DISABLED_PROMPT_PRESETS", "").split(",")
        if preset_id.strip()
    }
    return {
        preset["preset_id"]
        for preset in PROMPT_PRESETS
        if preset["enabled"] and preset["preset_id"] not in disabled
    }


def compose_analysis_prompt(prompt: str) -> tuple[str, list[dict[str, Any]]]:
    normalized_prompt = prompt.strip()
    enabled_ids = enabled_prompt_preset_ids()
    applied = [
        preset
        for preset in PROMPT_PRESETS
        if preset["enabled"] and preset["preset_id"] in enabled_ids
    ]
    if not applied:
        return normalized_prompt, []

    prompt_sections = [
        "Prompt presets:",
        *[
            f"- {preset['preset_id']}: {preset['prompt']}"
            for preset in applied
        ],
        "",
        "User prompt:",
        normalized_prompt,
    ]
    return "\n".join(prompt_sections), applied

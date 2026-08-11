from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .storage import load_run, save_run


FACE_TERMS = ("face", "facial", "人脸", "脸部", "露脸", "面部", "脸")
SWIFT_DETECTOR = Path(__file__).with_name("apple_face_detector.swift")


def is_face_prompt(prompt: str) -> bool:
    normalized = prompt.lower()
    return any(term in normalized for term in FACE_TERMS)


def build_face_detector_command(script_path: Path, image_paths: list[Path]) -> list[str]:
    return ["swift", str(script_path), *(str(path) for path in image_paths)]


def detect_face_paths(image_paths: list[Path]) -> dict[str, int] | None:
    if sys.platform != "darwin" or not image_paths or shutil.which("swift") is None:
        return None
    if not SWIFT_DETECTOR.exists():
        return None

    result = subprocess.run(
        build_face_detector_command(SWIFT_DETECTOR, image_paths),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None

    detected: dict[str, int] = {}
    try:
        for line in result.stdout.splitlines():
            item = json.loads(line)
            detected[str(Path(item["path"]).resolve())] = int(item["face_count"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    expected = {str(path.resolve()) for path in image_paths}
    if set(detected) != expected:
        return None
    return detected


def apply_face_prefilter(run_dir: Path, prompt: str) -> dict[str, Any]:
    run = load_run(run_dir)
    if not is_face_prompt(prompt):
        run["prefilter"] = {
            "type": "face",
            "status": "skipped",
            "reason": "Prompt does not require visible faces",
        }
        save_run(run_dir, run)
        return load_run(run_dir)

    sample_paths = [Path(item["path"]) for item in run["samples"]]
    detected = detect_face_paths(sample_paths)
    if detected is None:
        run["prefilter"] = {
            "type": "face",
            "status": "unavailable",
            "reason": "Apple Vision detector unavailable or failed; all ranges remain covered",
        }
        save_run(run_dir, run)
        return load_run(run_dir)

    positive_sample_ids = [
        item["sample_id"]
        for item in run["samples"]
        if detected.get(str(Path(item["path"]).resolve()), 0) > 0
    ]
    run["prefilter"] = {
        "type": "face",
        "status": "complete",
        "detector": "apple-vision",
        "sample_count": len(sample_paths),
        "positive_sample_count": len(positive_sample_ids),
        "positive_sample_ids": positive_sample_ids,
    }
    save_run(run_dir, run)
    return load_run(run_dir)

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .models import Asset, Sample

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm"}


def resolve_hwaccel(mode: str, platform: str | None = None) -> str | None:
    if mode not in {"auto", "none", "videotoolbox"}:
        raise ValueError(f"Unsupported hardware acceleration mode: {mode}")
    if mode == "none":
        return None
    if mode == "videotoolbox":
        return mode
    return "videotoolbox" if (platform or sys.platform) == "darwin" else None


def _float_fraction(value: str | None) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        if float(denominator) == 0:
            return 0.0
        return float(numerator) / float(denominator)
    return float(value)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def probe_media(path: Path) -> Asset:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    data: dict[str, Any] = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError(f"No video stream found: {path}")
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    size = path.stat().st_size
    digest = sha256_file(path)
    asset_id = f"{path.stem}-{digest[:12]}"
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0.0)
    return Asset(
        asset_id=asset_id,
        path=str(path.resolve()),
        sha256=digest,
        size_bytes=size,
        duration=duration,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=_float_fraction(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        video_codec=str(video.get("codec_name") or "unknown"),
        audio_codec=str(audio.get("codec_name")) if audio else None,
        has_audio=audio is not None,
    )


def find_video_files(input_dir: Path) -> list[Path]:
    if not input_dir.is_dir():
        raise NotADirectoryError(str(input_dir))
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in VIDEO_EXTENSIONS
        and not any(part.startswith(".") for part in path.relative_to(input_dir).parts)
    )


def build_sample_command(
    asset: Asset,
    output_pattern: Path,
    interval: float,
    width: int,
    hwaccel: str | None = None,
) -> list[str]:
    filter_graph = (
        f"fps=1/{interval},scale={width}:-2:"
        "force_original_aspect_ratio=decrease"
    )
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if hwaccel:
        command.extend(["-hwaccel", hwaccel])
    command.extend(
        [
            "-i",
            asset.path,
            "-map",
            "0:v:0",
            "-vf",
            filter_graph,
            "-q:v",
            "4",
            "-an",
            str(output_pattern),
        ]
    )
    return command


def extract_samples(
    asset: Asset,
    frames_dir: Path,
    interval: float = 1.0,
    width: int = 640,
    hwaccel: str | None = None,
) -> list[Sample]:
    if interval <= 0:
        raise ValueError("Sample interval must be positive")
    asset_dir = frames_dir / asset.asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(asset_dir.glob("*.jpg"))
    expected = max(1, int(asset.duration / interval) + 1)
    if len(existing) < expected:
        for old in existing:
            old.unlink()
        command = build_sample_command(
            asset,
            asset_dir / "%06d.jpg",
            interval,
            width,
            hwaccel,
        )
        subprocess.run(command, check=True)
        existing = sorted(asset_dir.glob("*.jpg"))

    samples: list[Sample] = []
    for index, frame_path in enumerate(existing):
        timestamp = min(index * interval, asset.duration)
        samples.append(
            Sample(
                sample_id=f"{asset.asset_id}-sample-{index:06d}",
                asset_id=asset.asset_id,
                timestamp=round(timestamp, 3),
                path=str(frame_path.resolve()),
            )
        )
    return samples

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from .storage import save_json


def _asset_map(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {asset["asset_id"]: asset for asset in run["assets"]}


def export_run(
    run: dict[str, Any],
    output_dir: Path,
    include_pending: bool = False,
    limit: int | None = None,
    transcode: bool = True,
    workers: int = 2,
) -> dict[str, Any]:
    if workers <= 0:
        raise ValueError("Workers must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = _asset_map(run)
    asset_order = {asset["asset_id"]: index for index, asset in enumerate(run["assets"])}
    candidates = [
        candidate
        for candidate in run.get("candidates", [])
        if include_pending or candidate["status"] == "accepted"
    ]
    candidates = sorted(candidates, key=lambda item: (asset_order[item["asset_id"]], item["start"]))
    if limit is not None:
        candidates = candidates[:limit]

    def export_segment(item: tuple[int, dict[str, Any]]) -> dict[str, Any]:
        index, candidate = item
        asset = assets[candidate["asset_id"]]
        stem = Path(asset["path"]).stem
        filename = f"{index:03d}_{stem}_{candidate['start']:.3f}-{candidate['end']:.3f}.mp4"
        target = output_dir / filename
        duration = candidate["end"] - candidate["start"]
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{candidate['start']:.3f}",
            "-i",
            asset["path"],
            "-t",
            f"{duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-movflags",
            "+faststart",
        ]
        if transcode:
            command.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k"])
        else:
            command.extend(["-c", "copy"])
        command.extend(["-y", str(target)])
        subprocess.run(command, check=True)
        return {
            **candidate,
            "source_path": asset["path"],
            "export_path": str(target.resolve()),
        }

    if candidates:
        with ThreadPoolExecutor(max_workers=min(workers, len(candidates))) as executor:
            exported = list(executor.map(export_segment, enumerate(candidates, start=1)))
    else:
        exported = []

    merged_path = _merge_segments(exported, output_dir)
    manifest = {
        "schema_version": 1,
        "run_id": run["run_id"],
        "prompt": run.get("prompt"),
        "provider": run.get("provider"),
        "segments": exported,
        "merged_path": str(merged_path.resolve()) if merged_path else None,
    }
    save_json(output_dir / "segments.json", manifest)
    save_json(output_dir / "run-report.json", run)
    _write_fcpxml(output_dir / "timeline.fcpxml", exported, assets)
    return manifest


def _merge_segments(segments: list[dict[str, Any]], output_dir: Path) -> Path | None:
    if not segments:
        return None

    def concat_entry(path: str) -> str:
        escaped = path.replace("'", "'\\''")
        return f"file '{escaped}'\n"

    list_path = output_dir / "merge-list.txt"
    list_path.write_text(
        "".join(concat_entry(segment["export_path"]) for segment in segments),
        encoding="utf-8",
    )
    merged_path = output_dir / "highlight-reel.mp4"
    base_command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
    ]
    try:
        subprocess.run(
            [*base_command, "-c", "copy", "-movflags", "+faststart", "-y", str(merged_path)],
            check=True,
        )
    except subprocess.CalledProcessError:
        subprocess.run(
            [
                *base_command,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                "-y",
                str(merged_path),
            ],
            check=True,
        )
    return merged_path


def _write_fcpxml(
    path: Path,
    segments: list[dict[str, Any]],
    assets: dict[str, dict[str, Any]],
) -> None:
    fcpxml = Element("fcpxml", version="1.10")
    resources = SubElement(fcpxml, "resources")
    format_node = SubElement(resources, "format", id="r-format", name="Video Highlight MVP")
    format_node.set("frameDuration", "1001/48000s")
    asset_ids: dict[str, str] = {}
    for index, asset in enumerate(assets.values(), start=1):
        resource_id = f"r-asset-{index}"
        asset_ids[asset["asset_id"]] = resource_id
        SubElement(
            resources,
            "asset",
            id=resource_id,
            name=Path(asset["path"]).name,
            src=Path(asset["path"]).as_uri(),
            duration=f"{asset['duration']:.3f}s",
            hasVideo="1",
            hasAudio="1" if asset["has_audio"] else "0",
            format="r-format",
        )
    library = SubElement(fcpxml, "library")
    event = SubElement(library, "event", name="Video Highlight MVP")
    project = SubElement(event, "project", name="Video Highlight MVP")
    sequence = SubElement(project, "sequence", format="r-format", duration="0s")
    spine = SubElement(sequence, "spine")
    offset = 0.0
    for segment in segments:
        duration = segment["end"] - segment["start"]
        SubElement(
            spine,
            "asset-clip",
            name=Path(assets[segment["asset_id"]]["path"]).name,
            ref=asset_ids[segment["asset_id"]],
            offset=f"{offset:.3f}s",
            start=f"{segment['start']:.3f}s",
            duration=f"{duration:.3f}s",
        )
        offset += duration
    sequence.set("duration", f"{offset:.3f}s")
    path.write_bytes(tostring(fcpxml, encoding="utf-8", xml_declaration=True))

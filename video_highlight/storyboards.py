from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Any

from .models import Sample
from .storage import load_run, save_json


def _frame_number(sample: Sample) -> int:
    try:
        return int(Path(sample.path).stem)
    except ValueError:
        return 1


def make_storyboard_specs(
    samples: list[Sample],
    cells_per_board: int = 60,
) -> list[dict[str, Any]]:
    if cells_per_board <= 0:
        raise ValueError("cells_per_board must be positive")
    by_asset: dict[str, list[Sample]] = {}
    for sample in samples:
        by_asset.setdefault(sample.asset_id, []).append(sample)

    specs: list[dict[str, Any]] = []
    for asset_id, asset_samples in by_asset.items():
        asset_samples.sort(key=lambda item: item.timestamp)
        for offset in range(0, len(asset_samples), cells_per_board):
            cells = asset_samples[offset : offset + cells_per_board]
            if not cells:
                continue
            minute_index = offset // cells_per_board
            specs.append(
                {
                    "storyboard_id": f"{asset_id}-minute-{minute_index:04d}",
                    "asset_id": asset_id,
                    "minute_index": minute_index,
                    "start": cells[0].timestamp,
                    "end": cells[-1].timestamp + 1.0,
                    "first_frame_number": _frame_number(cells[0]),
                    "cells": [
                        {
                            "cell_index": index,
                            "sample_id": sample.sample_id,
                            "timestamp": sample.timestamp,
                            "path": sample.path,
                        }
                        for index, sample in enumerate(cells)
                    ],
                }
            )
    return specs


def make_detail_storyboard_specs(
    samples: list[Sample],
    seconds_per_board: int = 30,
    cells_per_board: int = 12,
    active_sample_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if seconds_per_board <= 0 or cells_per_board <= 0:
        raise ValueError("seconds_per_board and cells_per_board must be positive")

    by_asset: dict[str, list[Sample]] = {}
    for sample in samples:
        by_asset.setdefault(sample.asset_id, []).append(sample)

    specs: list[dict[str, Any]] = []
    for asset_id, asset_samples in by_asset.items():
        asset_samples.sort(key=lambda item: item.timestamp)
        if not asset_samples:
            continue
        indexed_end = asset_samples[-1].timestamp + 1.0
        if active_sample_ids is None:
            starts = range(0, math.ceil(indexed_end), seconds_per_board)
        else:
            starts = sorted(
                {
                    int(sample.timestamp // seconds_per_board) * seconds_per_board
                    for sample in asset_samples
                    if sample.sample_id in active_sample_ids
                }
            )
        for start in starts:
            end = min(float(start + seconds_per_board), indexed_end)
            board_samples = [
                sample
                for sample in asset_samples
                if start <= sample.timestamp < end
                and (
                    active_sample_ids is None
                    or sample.sample_id in active_sample_ids
                )
            ]
            if not board_samples:
                continue
            duration = end - start
            cell_count = min(cells_per_board, len(board_samples), max(1, math.ceil(duration)))
            selected: list[Sample] = []
            used_sample_ids: set[str] = set()
            for index in range(cell_count):
                target = start + math.floor(duration * index / cell_count)
                available = [
                    sample
                    for sample in board_samples
                    if sample.sample_id not in used_sample_ids
                ]
                if not available:
                    break
                sample = min(
                    available,
                    key=lambda item: (abs(item.timestamp - target), item.timestamp),
                )
                selected.append(sample)
                used_sample_ids.add(sample.sample_id)
            specs.append(
                {
                    "storyboard_id": f"{asset_id}-detail-{start:04d}",
                    "asset_id": asset_id,
                    "detail_start": float(start),
                    "start": selected[0].timestamp,
                    "end": end,
                    "cells": [
                        {
                            "cell_index": index,
                            "sample_id": sample.sample_id,
                            "timestamp": sample.timestamp,
                            "path": sample.path,
                        }
                        for index, sample in enumerate(selected)
                    ],
                }
            )
    return specs


def create_storyboards(
    run_dir: Path,
    cells_per_board: int = 60,
    columns: int = 10,
    tile_width: int = 160,
) -> list[dict[str, Any]]:
    if columns <= 0 or tile_width <= 0:
        raise ValueError("columns and tile_width must be positive")
    run = load_run(run_dir)
    samples = [Sample(**item) for item in run["samples"]]
    specs = make_storyboard_specs(samples, cells_per_board)
    samples_by_id = {sample.sample_id: sample for sample in samples}
    rows = math.ceil(cells_per_board / columns)
    for spec in specs:
        first_sample = samples_by_id[spec["cells"][0]["sample_id"]]
        output = run_dir / "storyboards" / spec["asset_id"] / f"minute-{spec['minute_index']:04d}.jpg"
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists():
            filter_graph = (
                f"scale={tile_width}:90:force_original_aspect_ratio=decrease,"
                f"pad={tile_width}:90:(ow-iw)/2:(oh-ih)/2:black,"
                "drawtext=text='%{n}':x=3:y=3:fontsize=12:fontcolor=white:"
                "box=1:boxcolor=black@0.65,"
                f"tile={columns}x{rows}:padding=2:margin=4:color=#101827"
            )
            command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-framerate",
                "1",
                "-start_number",
                str(spec["first_frame_number"]),
                "-t",
                str(len(spec["cells"])),
                "-i",
                str(Path(first_sample.path).parent / "%06d.jpg"),
                "-vf",
                filter_graph,
                "-q:v",
                "3",
                "-y",
                str(output),
            ]
            subprocess.run(command, check=True)
        spec["image_path"] = str(output.resolve())
    save_json(run_dir / "storyboards.json", specs)
    return specs


def create_detail_storyboards(
    run_dir: Path,
    seconds_per_board: int = 30,
    cells_per_board: int = 12,
    columns: int = 4,
    tile_width: int = 320,
) -> list[dict[str, Any]]:
    if columns <= 0 or tile_width <= 0:
        raise ValueError("columns and tile_width must be positive")
    run = load_run(run_dir)
    samples = [Sample(**item) for item in run["samples"]]
    samples_by_id = {sample.sample_id: sample for sample in samples}
    prefilter = run.get("prefilter", {})
    active_sample_ids = None
    if (
        prefilter.get("type") == "face"
        and prefilter.get("status") == "complete"
    ):
        active_sample_ids = set(prefilter.get("positive_sample_ids", []))
    specs = make_detail_storyboard_specs(
        samples,
        seconds_per_board,
        cells_per_board,
        active_sample_ids,
    )
    rows = math.ceil(cells_per_board / columns)
    for spec in specs:
        first_sample = samples_by_id[spec["cells"][0]["sample_id"]]
        output = run_dir / "detail-storyboards" / spec["asset_id"] / f"{int(spec['detail_start']):04d}.jpg"
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists():
            first_frame_number = _frame_number(first_sample)
            offsets = [
                int(round(cell["timestamp"] - first_sample.timestamp))
                for cell in spec["cells"]
            ]
            select_expression = "+".join(f"eq(n,{offset})" for offset in offsets)
            filter_graph = (
                f"select='{select_expression}',"
                f"scale={tile_width}:180:force_original_aspect_ratio=decrease,"
                f"pad={tile_width}:180:(ow-iw)/2:(oh-ih)/2:black,"
                "drawtext=text='cell %{n}':x=4:y=4:fontsize=14:fontcolor=white:"
                "box=1:boxcolor=black@0.65,"
                f"tile={columns}x{rows}:padding=4:margin=8:color=#101827"
            )
            command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-framerate",
                "1",
                "-start_number",
                str(first_frame_number),
                "-t",
                str(max(offsets) + 1),
                "-i",
                str(Path(first_sample.path).parent / "%06d.jpg"),
                "-vf",
                filter_graph,
                "-vsync",
                "0",
                "-frames:v",
                "1",
                "-q:v",
                "3",
                "-y",
                str(output),
            ]
            subprocess.run(command, check=True)
        spec["image_path"] = str(output.resolve())
    save_json(run_dir / "detail-storyboards.json", specs)
    return specs


def build_storyboard_batches(
    run_dir: Path,
    batch_size: int = 5,
    cells_per_board: int = 60,
) -> list[dict[str, Any]]:
    if batch_size <= 0:
        raise ValueError("Batch size must be positive")
    specs = create_storyboards(run_dir, cells_per_board)
    batches: list[dict[str, Any]] = []
    for index in range(0, len(specs), batch_size):
        selected = specs[index : index + batch_size]
        batches.append(
            {
                "batch_id": f"storyboard-batch-{len(batches):04d}",
                "mode": "storyboard",
                "storyboards": [
                    {
                        "storyboard_id": spec["storyboard_id"],
                        "asset_id": spec["asset_id"],
                        "start": spec["start"],
                        "end": spec["end"],
                        "image_path": spec["image_path"],
                        "cells": spec["cells"],
                    }
                    for spec in selected
                ],
            }
        )
    return batches


def build_detail_storyboard_batches(
    run_dir: Path,
    batch_size: int = 5,
    seconds_per_board: int = 30,
    cells_per_board: int = 12,
) -> list[dict[str, Any]]:
    if batch_size <= 0:
        raise ValueError("Batch size must be positive")
    specs = create_detail_storyboards(run_dir, seconds_per_board, cells_per_board)
    batches: list[dict[str, Any]] = []
    for index in range(0, len(specs), batch_size):
        selected = specs[index : index + batch_size]
        batches.append(
            {
                "batch_id": f"detail-storyboard-batch-{len(batches):04d}",
                "mode": "detail-storyboard",
                "storyboards": [
                    {
                        "storyboard_id": spec["storyboard_id"],
                        "asset_id": spec["asset_id"],
                        "start": spec["start"],
                        "end": spec["end"],
                        "image_path": spec["image_path"],
                        "cells": spec["cells"],
                    }
                    for spec in selected
                ],
            }
        )
    return batches

from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .media import extract_samples, find_video_files, probe_media, resolve_hwaccel
from .models import Asset, Sample, to_jsonable
from .segments import build_windows
from .storage import save_run


def create_run(
    input_dir: Path,
    runs_dir: Path,
    interval: float = 1.0,
    sample_width: int = 640,
    workers: int = 2,
    hwaccel: str = "auto",
) -> Path:
    if workers <= 0:
        raise ValueError("Workers must be positive")
    resolved_hwaccel = resolve_hwaccel(hwaccel)
    timestamp = datetime.now(timezone.utc)
    run_id = timestamp.strftime("run-%Y%m%d-%H%M%S-%f")
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    assets: list[Asset] = []
    samples: list[Sample] = []
    files = find_video_files(input_dir)
    if not files:
        raise ValueError(f"No supported video files found in {input_dir}")

    def scan_file(path: Path) -> tuple[Asset, list[Sample]]:
        asset = probe_media(path)
        extracted = extract_samples(
            asset,
            run_dir / "frames",
            interval,
            sample_width,
            resolved_hwaccel,
        )
        return asset, extracted

    with ThreadPoolExecutor(max_workers=min(workers, len(files))) as executor:
        results = list(executor.map(scan_file, files))
    for asset, extracted in results:
        assets.append(asset)
        samples.extend(extracted)

    windows = build_windows(samples)
    run: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(input_dir.resolve()),
        "prompt": None,
        "provider": None,
        "settings": {
            "sample_interval": interval,
            "sample_width": sample_width,
            "hwaccel": resolved_hwaccel,
            "window_seconds": 4.0,
            "window_stride_seconds": 3.0,
            "padding_seconds": 1.0,
            "merge_gap_seconds": 0.5,
            "minimum_segment_seconds": 2.0,
        },
        "assets": [to_jsonable(item) for item in assets],
        "samples": [to_jsonable(item) for item in samples],
        "windows": [to_jsonable(item) for item in windows],
        "candidates": [],
        "analysis_error": None,
    }
    save_run(run_dir, run)
    return run_dir

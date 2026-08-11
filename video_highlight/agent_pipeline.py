from __future__ import annotations

from pathlib import Path
from typing import Any

from .analysis import _persist_decisions
from .models import Asset, Candidate, Sample, Window, validate_model_decisions
from .modes import resolve_mode
from .segments import build_candidate_windows, merge_candidates
from .storage import load_json, load_run, save_run
from .storyboards import build_storyboard_batches


def build_batches(
    run_dir: Path,
    batch_size: int = 8,
    only_candidates: bool = False,
) -> list[dict[str, Any]]:
    if batch_size <= 0:
        raise ValueError("Batch size must be positive")
    run = load_run(run_dir)
    samples = {item["sample_id"]: Sample(**item) for item in run["samples"]}
    all_samples = list(samples.values())
    windows = [Window(**item) for item in run["windows"]]
    if only_candidates:
        candidates = [Candidate(**item) for item in run.get("candidates", [])]
        windows = build_candidate_windows(
            all_samples,
            candidates,
            window_seconds=float(run["settings"].get("window_seconds", 4.0)),
        )
    run["analysis_windows"] = [
        {
            "window_id": window.window_id,
            "asset_id": window.asset_id,
            "start": window.start,
            "end": window.end,
            "sample_ids": window.sample_ids,
        }
        for window in windows
    ]
    save_run(run_dir, run)
    batches: list[dict[str, Any]] = []
    for index in range(0, len(windows), batch_size):
        batch_windows = windows[index : index + batch_size]
        batches.append(
            {
                "batch_id": f"batch-{len(batches):04d}",
                "windows": [
                    {
                        "window_id": window.window_id,
                        "asset_id": window.asset_id,
                        "start": window.start,
                        "end": window.end,
                        "sample_ids": window.sample_ids,
                        "samples": [
                            {
                                "sample_id": sample_id,
                                "timestamp": samples[sample_id].timestamp,
                                "path": samples[sample_id].path,
                            }
                            for sample_id in window.sample_ids
                        ],
                    }
                    for window in batch_windows
                ],
            }
        )
    return batches


def apply_storyboard_decisions(
    run_dir: Path,
    prompt: str,
    decisions_path: Path,
    merge_existing: bool = False,
    mode: str | None = None,
) -> dict[str, Any]:
    raw = load_json(decisions_path)
    if isinstance(raw, dict):
        raw = raw.get("storyboards")
    if not isinstance(raw, list):
        raise ValueError("Storyboard decisions must be a JSON array")
    run = load_run(run_dir)
    specs_path = run_dir / "detail-storyboards.json"
    if not specs_path.exists():
        specs_path = run_dir / "storyboards.json"
    specs = {item["storyboard_id"]: item for item in load_json(specs_path)}
    assets = {item["asset_id"]: Asset(**item) for item in run["assets"]}
    raw_candidates: dict[str, list[Candidate]] = {}
    seen_cells: set[tuple[str, int]] = set()
    for item in raw:
        storyboard_id = item.get("storyboard_id")
        if storyboard_id not in specs:
            raise ValueError(f"Unknown storyboard_id: {storyboard_id}")
        spec = specs[storyboard_id]
        keep_cells = item.get("keep_cells")
        if keep_cells is None:
            keep_cells = [
                cell.get("cell_index")
                for cell in item.get("cells", [])
                if cell.get("keep") is True
            ]
        if not isinstance(keep_cells, list) or not all(isinstance(cell, int) for cell in keep_cells):
            raise ValueError(f"Invalid keep_cells for {storyboard_id}")
        score = item.get("score", 0.5)
        tags = item.get("tags", ["storyboard-candidate"])
        reason = item.get("reason", "Selected by storyboard review")
        if not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
            raise ValueError(f"Invalid score for {storyboard_id}")
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError(f"Invalid tags for {storyboard_id}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"Invalid reason for {storyboard_id}")
        cell_map = {cell["cell_index"]: cell for cell in spec["cells"]}
        for cell_index in keep_cells:
            key = (storyboard_id, cell_index)
            if key in seen_cells:
                raise ValueError(f"Duplicate storyboard cell: {storyboard_id}/{cell_index}")
            seen_cells.add(key)
            cell = cell_map.get(cell_index)
            if cell is None:
                raise ValueError(f"Unknown cell_index for {storyboard_id}: {cell_index}")
            raw_candidates.setdefault(spec["asset_id"], []).append(
                Candidate(
                    candidate_id=f"storyboard-{storyboard_id}-{cell_index}",
                    asset_id=spec["asset_id"],
                    start=cell["timestamp"],
                    end=cell["timestamp"] + 1.0,
                    score=float(score),
                    tags=tags,
                    reason=reason.strip(),
                    source_window_ids=[storyboard_id],
                )
            )

    candidates: list[Candidate] = []
    settings = run["settings"]
    for asset_id, asset_candidates in raw_candidates.items():
        candidates.extend(
            merge_candidates(
                asset_candidates,
                asset_duration=assets[asset_id].duration,
                padding=max(float(settings["padding_seconds"]), 1.5),
                merge_gap=float(settings["merge_gap_seconds"]),
                minimum_duration=float(settings["minimum_segment_seconds"]),
            )
        )
    if merge_existing:
        existing_by_asset: dict[str, list[Candidate]] = {}
        for item in run.get("candidates", []):
            existing = Candidate(**item)
            existing_by_asset.setdefault(existing.asset_id, []).append(existing)
        merged_candidates: list[Candidate] = []
        for asset_id, existing in existing_by_asset.items():
            combined = existing + [candidate for candidate in candidates if candidate.asset_id == asset_id]
            merged_candidates.extend(
                merge_candidates(
                    combined,
                    asset_duration=assets[asset_id].duration,
                    padding=0.0,
                    merge_gap=float(settings["merge_gap_seconds"]),
                    minimum_duration=float(settings["minimum_segment_seconds"]),
                )
            )
        for asset_id, asset_candidates in raw_candidates.items():
            if asset_id not in existing_by_asset:
                merged_candidates.extend(candidate for candidate in candidates if candidate.asset_id == asset_id)
        candidates = merged_candidates
    for index, candidate in enumerate(sorted(candidates, key=lambda item: (item.asset_id, item.start))):
        candidate.candidate_id = f"candidate-{index:06d}"
    run["prompt"] = prompt.strip()
    run["mode"] = resolve_mode(prompt, mode)
    run["quality_mode"] = run["mode"]
    run["provider"] = "agent-storyboard"
    run["model"] = "codex-subagent"
    run["analysis_mode"] = "detail-storyboard" if "detail" in specs_path.name else "storyboard"
    run["analysis_storyboard_count"] = len(specs)
    run["analysis_windows"] = []
    run["candidates"] = candidates
    run["analysis_error"] = None
    save_run(run_dir, run)
    return load_run(run_dir)


def apply_agent_decisions(
    run_dir: Path,
    prompt: str,
    decisions_path: Path,
) -> dict[str, Any]:
    raw = load_json(decisions_path)
    if isinstance(raw, dict):
        raw = raw.get("decisions")
    if not isinstance(raw, list):
        raise ValueError("Agent decisions must be a JSON array")
    run = load_run(run_dir)
    analysis_windows = run.get("analysis_windows") or run["windows"]
    known_window_ids = {item["window_id"] for item in analysis_windows}
    decisions = validate_model_decisions(raw, known_window_ids)
    if len({decision.window_id for decision in decisions}) != len(decisions):
        raise ValueError("Duplicate window_id across agent decisions")
    return _persist_decisions(
        run_dir,
        prompt.strip(),
        "agent",
        "codex-subagent",
        decisions,
        windows_data=analysis_windows,
    )

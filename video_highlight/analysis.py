from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .models import Asset, Candidate, ModelDecision, Sample, Window, validate_model_decisions
from .providers import make_provider
from .segments import merge_candidates
from .storage import load_run, save_run


def analyze_run(
    run_dir: Path,
    prompt: str,
    provider_name: str = "mock",
    max_windows: int | None = None,
) -> dict[str, Any]:
    if not prompt.strip():
        raise ValueError("Prompt cannot be empty")
    run = load_run(run_dir)
    assets = {item["asset_id"]: Asset(**item) for item in run["assets"]}
    samples = {item["sample_id"]: Sample(**item) for item in run["samples"]}
    windows = [Window(**item) for item in run["windows"]]
    if max_windows is not None:
        windows = windows[:max_windows]

    provider = make_provider(provider_name)
    decisions = provider.analyze(prompt.strip(), windows, samples)
    return _persist_decisions(run_dir, prompt.strip(), provider.name, os.environ.get("HIGHLIGHT_MODEL") or "mock-v1", decisions)


def _persist_decisions(
    run_dir: Path,
    prompt: str,
    provider_name: str,
    model_name: str,
    decisions: list[ModelDecision],
    windows_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    run = load_run(run_dir)
    assets = {item["asset_id"]: Asset(**item) for item in run["assets"]}
    windows = [Window(**item) for item in (windows_data or run["windows"])]
    windows_by_id = {window.window_id: window for window in windows}
    raw_candidates: dict[str, list[Candidate]] = {}
    for decision in decisions:
        if not decision.keep:
            continue
        window = windows_by_id[decision.window_id]
        raw_candidates.setdefault(window.asset_id, []).append(
            Candidate(
                candidate_id=f"raw-{decision.window_id}",
                asset_id=window.asset_id,
                start=window.start,
                end=window.end,
                score=decision.score,
                tags=decision.tags,
                reason=decision.reason,
                source_window_ids=[window.window_id],
            )
        )

    candidates: list[Candidate] = []
    settings = run["settings"]
    for asset_id, asset_candidates in raw_candidates.items():
        candidates.extend(
            merge_candidates(
                asset_candidates,
                asset_duration=assets[asset_id].duration,
                padding=float(settings["padding_seconds"]),
                merge_gap=float(settings["merge_gap_seconds"]),
                minimum_duration=float(settings["minimum_segment_seconds"]),
            )
        )
    for index, candidate in enumerate(
        sorted(candidates, key=lambda item: (item.asset_id, item.start))
    ):
        candidate.candidate_id = f"candidate-{index:06d}"

    run["prompt"] = prompt.strip()
    run["provider"] = provider_name
    run["model"] = model_name
    run["analysis_mode"] = "frames"
    run["analysis_window_count"] = len(windows)
    run["candidates"] = candidates
    run["analysis_error"] = None
    save_run(run_dir, run)
    return load_run(run_dir)

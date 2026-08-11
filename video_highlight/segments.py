from __future__ import annotations

from collections.abc import Iterable

from .models import Candidate, Sample, Window


def build_windows(
    samples: list[Sample],
    window_seconds: float = 4.0,
    stride_seconds: float = 3.0,
) -> list[Window]:
    by_asset: dict[str, list[Sample]] = {}
    for sample in samples:
        by_asset.setdefault(sample.asset_id, []).append(sample)

    windows: list[Window] = []
    for asset_id, asset_samples in by_asset.items():
        asset_samples.sort(key=lambda item: item.timestamp)
        if not asset_samples:
            continue
        start = asset_samples[0].timestamp
        last_timestamp = asset_samples[-1].timestamp
        while start <= last_timestamp:
            end = start + window_seconds
            in_window = [
                sample.sample_id
                for sample in asset_samples
                if start <= sample.timestamp < end
            ]
            if in_window:
                window_id = f"{asset_id}-{len(windows):06d}"
                windows.append(Window(window_id, asset_id, start, end, in_window))
            start += stride_seconds
    return windows


def build_candidate_windows(
    samples: list[Sample],
    candidates: Iterable[Candidate],
    window_seconds: float = 4.0,
) -> list[Window]:
    """Tile candidate ranges into non-overlapping windows for final review."""
    if window_seconds <= 0:
        raise ValueError("Window size must be positive")

    samples_by_asset: dict[str, list[Sample]] = {}
    for sample in samples:
        samples_by_asset.setdefault(sample.asset_id, []).append(sample)
    for asset_samples in samples_by_asset.values():
        asset_samples.sort(key=lambda item: item.timestamp)

    ranges_by_asset: dict[str, list[tuple[float, float]]] = {}
    for candidate in candidates:
        if candidate.end <= candidate.start:
            continue
        ranges_by_asset.setdefault(candidate.asset_id, []).append(
            (candidate.start, candidate.end)
        )

    windows: list[Window] = []
    for asset_id in samples_by_asset:
        ranges = sorted(ranges_by_asset.get(asset_id, []))
        if not ranges:
            continue

        merged_ranges: list[tuple[float, float]] = []
        for start, end in ranges:
            if merged_ranges and start <= merged_ranges[-1][1]:
                previous_start, previous_end = merged_ranges[-1]
                merged_ranges[-1] = (previous_start, max(previous_end, end))
            else:
                merged_ranges.append((start, end))

        asset_samples = samples_by_asset[asset_id]
        asset_index = 0
        asset_window_index = 0
        for range_start, range_end in merged_ranges:
            start = range_start
            while start < range_end:
                end = start + window_seconds
                while asset_index < len(asset_samples) and asset_samples[asset_index].timestamp < start:
                    asset_index += 1
                sample_ids: list[str] = []
                sample_index = asset_index
                while sample_index < len(asset_samples):
                    sample = asset_samples[sample_index]
                    if sample.timestamp >= end:
                        break
                    if sample.timestamp < range_end:
                        sample_ids.append(sample.sample_id)
                    sample_index += 1
                if sample_ids:
                    windows.append(
                        Window(
                            window_id=f"{asset_id}-candidate-{asset_window_index:06d}",
                            asset_id=asset_id,
                            start=start,
                            end=end,
                            sample_ids=sample_ids,
                        )
                    )
                    asset_window_index += 1
                start = end

    return windows


def merge_candidates(
    candidates: Iterable[Candidate],
    asset_duration: float,
    padding: float = 1.0,
    merge_gap: float = 0.5,
    minimum_duration: float = 2.0,
) -> list[Candidate]:
    ordered = sorted(candidates, key=lambda item: (item.start, item.end))
    merged: list[Candidate] = []
    for candidate in ordered:
        start = max(0.0, candidate.start - padding)
        end = min(asset_duration, candidate.end + padding)
        if end - start < minimum_duration:
            continue

        if merged and start <= merged[-1].end + merge_gap:
            previous = merged[-1]
            previous.end = max(previous.end, end)
            previous.score = max(previous.score, candidate.score)
            previous.tags = list(dict.fromkeys(previous.tags + candidate.tags))
            previous.source_window_ids.extend(candidate.source_window_ids)
            if candidate.reason not in previous.reason:
                previous.reason = f"{previous.reason}; {candidate.reason}"
            continue

        merged.append(
            Candidate(
                candidate_id=f"candidate-{len(merged):06d}",
                asset_id=candidate.asset_id,
                start=start,
                end=end,
                score=candidate.score,
                tags=list(dict.fromkeys(candidate.tags)),
                reason=candidate.reason,
                status=candidate.status,
                source_window_ids=list(candidate.source_window_ids),
            )
        )
    return merged

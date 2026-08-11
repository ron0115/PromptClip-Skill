from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelDecision:
    window_id: str
    keep: bool
    score: float
    tags: list[str]
    reason: str


@dataclass
class Asset:
    asset_id: str
    path: str
    sha256: str
    size_bytes: int
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str | None
    has_audio: bool


@dataclass
class Sample:
    sample_id: str
    asset_id: str
    timestamp: float
    path: str


@dataclass
class Window:
    window_id: str
    asset_id: str
    start: float
    end: float
    sample_ids: list[str]


@dataclass
class Candidate:
    candidate_id: str
    asset_id: str
    start: float
    end: float
    score: float
    tags: list[str]
    reason: str
    status: str = "pending"
    source_window_ids: list[str] = field(default_factory=list)


def validate_model_decisions(
    raw_decisions: list[dict[str, Any]], known_window_ids: set[str]
) -> list[ModelDecision]:
    decisions: list[ModelDecision] = []
    seen: set[str] = set()
    for raw in raw_decisions:
        window_id = raw.get("window_id")
        if not isinstance(window_id, str) or window_id not in known_window_ids:
            raise ValueError(f"Unknown window_id: {window_id!r}")
        if window_id in seen:
            raise ValueError(f"Duplicate window_id: {window_id}")

        keep = raw.get("keep")
        score = raw.get("score")
        tags = raw.get("tags")
        reason = raw.get("reason")
        if not isinstance(keep, bool):
            raise ValueError(f"Invalid keep for {window_id}")
        if not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
            raise ValueError(f"Invalid score for {window_id}")
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError(f"Invalid tags for {window_id}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"Invalid reason for {window_id}")

        decisions.append(ModelDecision(window_id, keep, float(score), tags, reason.strip()))
        seen.add(window_id)
    return decisions


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value

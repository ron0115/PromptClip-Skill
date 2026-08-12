from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from functools import lru_cache
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from .storage import save_json


_STRATEGY_NONE = "none"
_STRATEGY_STREAM_COPY = "stream_copy"
_STRATEGY_SINGLE_TRANSCODE = "single_transcode"
_STRATEGY_COMPATIBILITY_TRANSCODE = "compatibility_transcode"
_PROFILE_PLATFORM = "platform"
_PROFILE_SOURCE = "source"
_ENCODER_H264_VIDEOTOOLBOX = "h264_videotoolbox"
_ENCODER_LIBX264 = "libx264"
_PROBE_FIELDS = (
    "codec_name",
    "codec_tag_string",
    "profile",
    "level",
    "width",
    "height",
    "pix_fmt",
    "field_order",
    "sample_aspect_ratio",
    "color_range",
    "color_space",
    "color_transfer",
    "color_primaries",
    "avg_frame_rate",
    "r_frame_rate",
    "time_base",
    "sample_fmt",
    "sample_rate",
    "channels",
    "channel_layout",
)


def default_export_dir(run: dict[str, Any]) -> Path:
    source_dirs = [Path(asset["path"]).resolve().parent for asset in run.get("assets", [])]
    if not source_dirs:
        raise ValueError("Cannot infer export directory for a run without assets")
    source_root = Path(os.path.commonpath([str(path) for path in source_dirs]))
    return source_root / "PromptClip-Highlights" / str(run["run_id"])


def _asset_map(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {asset["asset_id"]: asset for asset in run["assets"]}


def export_run(
    run: dict[str, Any],
    output_dir: Path,
    include_pending: bool = False,
    limit: int | None = None,
    transcode: bool | None = None,
    workers: int = 2,
    mode: str | None = None,
    export_profile: str = _PROFILE_SOURCE,
) -> dict[str, Any]:
    if workers <= 0:
        raise ValueError("Workers must be positive")
    if mode is not None:
        resolved_mode = mode
    elif include_pending:
        resolved_mode = "fast"
    else:
        resolved_mode = run.get("mode") or run.get("quality_mode") or "precise"
    if resolved_mode not in {"fast", "precise"}:
        raise ValueError("Mode must be fast or precise")
    if resolved_mode == "precise" and include_pending:
        raise ValueError("Precise mode requires accepted candidates")
    if resolved_mode == "fast" and not include_pending:
        raise ValueError("Fast mode requires include_pending candidates")
    if export_profile not in {_PROFILE_PLATFORM, _PROFILE_SOURCE}:
        raise ValueError("Export profile must be platform or source")
    run["mode"] = resolved_mode
    run["quality_mode"] = resolved_mode
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

    exported = [_segment_record(candidate, assets[candidate["asset_id"]]) for candidate in candidates]
    probes = _probe_sources(exported)
    audio_settings = _audio_settings(probes, exported)
    video_encoder = _choose_video_encoder(export_profile)
    if export_profile == _PROFILE_PLATFORM:
        transcode = True
    if (
        export_profile == _PROFILE_SOURCE
        and resolved_mode == "fast"
        and transcode is not True
        and _sources_are_compatible(exported, probes)
    ):
        exported = _snap_segments_to_keyframes(exported, probes)
    strategy = _select_export_strategy(exported, probes, transcode)
    merged_path, strategy = _export_timeline(exported, assets, probes, audio_settings, video_encoder, output_dir, strategy)
    manifest = {
        "schema_version": 1,
        "run_id": run["run_id"],
        "prompt": run.get("prompt"),
        "provider": run.get("provider"),
        "mode": resolved_mode,
        "export_profile": export_profile,
        "video_encoder": video_encoder,
        "target_audio_bitrate": audio_settings.get("bit_rate"),
        "target_audio_sample_rate": audio_settings.get("sample_rate"),
        "target_audio_channels": audio_settings.get("channels"),
        "export_strategy": strategy,
        "source_preserved": strategy == _STRATEGY_STREAM_COPY,
        "reencoded": strategy in {_STRATEGY_SINGLE_TRANSCODE, _STRATEGY_COMPATIBILITY_TRANSCODE},
        "segments": exported,
        "merged_path": str(merged_path.resolve()) if merged_path else None,
    }
    save_json(output_dir / "segments.json", manifest)
    save_json(output_dir / "run-report.json", run)
    _write_fcpxml(output_dir / "timeline.fcpxml", exported, assets)
    return manifest


def _segment_record(candidate: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    start = max(0.0, float(candidate["start"]))
    duration = float(asset.get("duration") or 0.0)
    end = min(float(candidate["end"]), duration) if duration > 0 else float(candidate["end"])
    if end <= start:
        raise ValueError(f"Invalid candidate range: {candidate['candidate_id']}")
    return {
        **candidate,
        "start": round(start, 3),
        "end": round(end, 3),
        "source_path": str(Path(asset["path"]).resolve()),
    }


def _probe_json(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def _probe_sources(segments: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    paths = dict.fromkeys(segment["source_path"] for segment in segments)
    probes: dict[str, dict[str, Any]] = {}
    for path in paths:
        stream_data = _probe_json(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                path,
            ]
        )
        streams = stream_data.get("streams", [])
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        video, video_ordinal = _select_primary_video(video_streams)
        if video is None:
            raise ValueError(f"No video stream found: {path}")
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        audio = audio_streams[0] if audio_streams else None
        probes[path] = {
            "video": _stream_signature(video),
            "audio": _stream_signature(audio) if audio else None,
            "audio_raw": audio or {},
            "duration": float(stream_data.get("format", {}).get("duration") or video.get("duration") or 0.0),
            "keyframes": _probe_keyframes(path, f"v:{video_ordinal}"),
            "video_selector": f"v:{video_ordinal}",
            "audio_selector": "a:0" if audio else None,
            "stream_layout": (len(video_streams), len(audio_streams), video_ordinal, 0 if audio else None),
        }
    return probes


def _audio_settings(probes: dict[str, dict[str, Any]], segments: list[dict[str, Any]]) -> dict[str, Any]:
    if not segments:
        return {"bit_rate": 160000, "sample_rate": 48000, "channels": 2, "channel_layout": "stereo"}
    first_probe = probes[segments[0]["source_path"]]
    audio = first_probe.get("audio_raw") or {}
    bit_rate = audio.get("bit_rate")
    sample_rate = audio.get("sample_rate")
    channels = audio.get("channels")
    channel_layout = audio.get("channel_layout")
    return {
        "bit_rate": int(float(bit_rate)) if bit_rate not in (None, "") else 160000,
        "sample_rate": int(sample_rate) if sample_rate not in (None, "") else 48000,
        "channels": int(channels) if channels not in (None, "") else 2,
        "channel_layout": str(channel_layout) if channel_layout not in (None, "") else "stereo",
    }


def _choose_video_encoder(export_profile: str) -> str:
    if export_profile == _PROFILE_PLATFORM and shutil.which("ffmpeg"):
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                check=True,
                capture_output=True,
                text=True,
            )
            if _ENCODER_H264_VIDEOTOOLBOX in result.stdout:
                return _ENCODER_H264_VIDEOTOOLBOX
        except subprocess.CalledProcessError:
            pass
    return _ENCODER_LIBX264


@lru_cache(maxsize=1)
def _supports_videotoolbox_hwaccel() -> bool:
    if not shutil.which("ffmpeg"):
        return False
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-hwaccels"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return False
    return "videotoolbox" in result.stdout


def _sources_are_compatible(
    segments: list[dict[str, Any]],
    probes: dict[str, dict[str, Any]],
) -> bool:
    paths = {segment["source_path"] for segment in segments}
    return len(
        {
            (probes[path]["video"], probes[path]["audio"], probes[path]["stream_layout"])
            for path in paths
        }
    ) == 1


def _select_primary_video(streams: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, int]:
    if not streams:
        return None, 0
    auxiliary_terms = ("preview", "thumbnail", "cover")
    primary: list[tuple[int, dict[str, Any]]] = []
    for ordinal, stream in enumerate(streams):
        disposition = stream.get("disposition") or {}
        tags = stream.get("tags") or {}
        handler_name = str(tags.get("handler_name") or "").lower()
        is_attached = bool(disposition.get("attached_pic"))
        is_auxiliary = is_attached or any(term in handler_name for term in auxiliary_terms)
        if not is_auxiliary:
            primary.append((ordinal, stream))
    candidates = primary or list(enumerate(streams))

    def rank(item: tuple[int, dict[str, Any]]) -> tuple[int, int, float, float]:
        _, stream = item
        disposition = stream.get("disposition") or {}
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        try:
            bit_rate = float(stream.get("bit_rate") or 0)
        except (TypeError, ValueError):
            bit_rate = 0.0
        try:
            duration = float(stream.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0.0
        return (int(bool(disposition.get("default"))), width * height, bit_rate, duration)

    selected_ordinal, selected_stream = max(candidates, key=rank)
    return selected_stream, selected_ordinal


def _stream_signature(stream: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if stream is None:
        return None
    return tuple(stream.get(field) for field in _PROBE_FIELDS)


def _probe_keyframes(path: str, selector: str) -> list[float]:
    data = _probe_json(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            selector,
            "-show_packets",
            "-show_entries",
            "packet=pts_time,dts_time,flags",
            "-of",
            "json",
            path,
        ]
    )
    timestamps: list[float] = []
    for packet in data.get("packets", []):
        if "K" not in str(packet.get("flags", "")):
            continue
        for field in ("pts_time", "dts_time"):
            value = packet.get(field)
            if value not in (None, "N/A"):
                timestamps.append(float(value))
                break
    return timestamps


def _select_export_strategy(
    segments: list[dict[str, Any]],
    probes: dict[str, dict[str, Any]],
    transcode: bool | None,
) -> str:
    if not segments:
        return _STRATEGY_NONE
    compatible = _sources_are_compatible(segments, probes)
    if transcode is True:
        return _STRATEGY_SINGLE_TRANSCODE if compatible else _STRATEGY_COMPATIBILITY_TRANSCODE
    if not compatible:
        return _STRATEGY_COMPATIBILITY_TRANSCODE
    if all(_segment_is_keyframe_safe(segment, probes[segment["source_path"]]) for segment in segments):
        return _STRATEGY_STREAM_COPY
    return _STRATEGY_SINGLE_TRANSCODE


def _segment_is_keyframe_safe(segment: dict[str, Any], probe: dict[str, Any]) -> bool:
    duration = probe["duration"]
    keyframes = probe["keyframes"]
    tolerance = 0.005
    start = float(segment["start"])
    end = float(segment["end"])
    start_safe = abs(start) <= tolerance or any(abs(start - point) <= tolerance for point in keyframes)
    end_safe = abs(end - duration) <= tolerance or any(abs(end - point) <= tolerance for point in keyframes)
    return start_safe and end_safe


def _snap_segments_to_keyframes(
    segments: list[dict[str, Any]],
    probes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    snapped = [_snap_segment_to_keyframes(segment, probes[segment["source_path"]]) for segment in segments]
    return _merge_overlapping_export_segments(snapped)


def _snap_segment_to_keyframes(segment: dict[str, Any], probe: dict[str, Any]) -> dict[str, Any]:
    keyframes = probe["keyframes"]
    if not keyframes:
        return segment
    duration = float(probe["duration"])
    requested_start = float(segment["start"])
    requested_end = float(segment["end"])
    start = _previous_keyframe(requested_start, keyframes)
    end = _next_keyframe(requested_end, keyframes, duration)
    if end <= start:
        end = _next_keyframe(start + 0.001, keyframes, duration)
    snapped = dict(segment)
    snapped["requested_start"] = round(requested_start, 3)
    snapped["requested_end"] = round(requested_end, 3)
    snapped["start"] = round(max(0.0, start), 3)
    snapped["end"] = round(min(duration, end), 3)
    snapped["keyframe_snapped"] = (
        abs(snapped["start"] - requested_start) > 0.005
        or abs(snapped["end"] - requested_end) > 0.005
    )
    return snapped


def _previous_keyframe(timestamp: float, keyframes: list[float]) -> float:
    previous = keyframes[0]
    for keyframe in keyframes:
        if keyframe > timestamp:
            break
        previous = keyframe
    return previous


def _next_keyframe(timestamp: float, keyframes: list[float], duration: float) -> float:
    for keyframe in keyframes:
        if keyframe >= timestamp:
            return keyframe
    return duration


def _merge_overlapping_export_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not segments:
        return []
    merged: list[dict[str, Any]] = []
    for segment in segments:
        if (
            merged
            and merged[-1]["source_path"] == segment["source_path"]
            and float(segment["start"]) <= float(merged[-1]["end"]) + 0.001
        ):
            current = merged[-1]
            current["end"] = round(max(float(current["end"]), float(segment["end"])), 3)
            current["requested_start"] = round(
                min(float(current.get("requested_start", current["start"])), float(segment.get("requested_start", segment["start"]))),
                3,
            )
            current["requested_end"] = round(
                max(float(current.get("requested_end", current["end"])), float(segment.get("requested_end", segment["end"]))),
                3,
            )
            current["keyframe_snapped"] = bool(current.get("keyframe_snapped") or segment.get("keyframe_snapped"))
            current["source_window_ids"] = list(
                dict.fromkeys(current.get("source_window_ids", []) + segment.get("source_window_ids", []))
            )
            current["tags"] = list(dict.fromkeys(current.get("tags", []) + segment.get("tags", [])))
            continue
        merged.append(dict(segment))
    for index, segment in enumerate(merged):
        if index < len(segments):
            segment["candidate_id"] = segments[index]["candidate_id"]
        else:
            segment["candidate_id"] = f"export-segment-{index:06d}"
    return merged


def _write_concat_list(segments: list[dict[str, Any]], output_dir: Path) -> Path:
    def escape(path: str) -> str:
        return path.replace("\\", "\\\\").replace("'", "'\\''")

    list_path = output_dir / "merge-list.txt"
    lines = ["ffconcat version 1.0\n"]
    for segment in segments:
        lines.extend(
            [
                f"file '{escape(segment['source_path'])}'\n",
                f"inpoint {float(segment['start']):.3f}\n",
                f"outpoint {float(segment['end']):.3f}\n",
            ]
        )
    list_path.write_text("".join(lines), encoding="utf-8")
    return list_path


def _concat_command(
    list_path: Path,
    output: Path,
    transcode: bool,
    probe: dict[str, Any],
    video_encoder: str,
    audio_settings: dict[str, Any],
    use_hwaccel: bool = False,
) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if use_hwaccel and _supports_videotoolbox_hwaccel():
        command.extend(["-hwaccel", "videotoolbox"])
    command.extend([
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-map",
        f"0:{probe['video_selector']}",
        "-sn",
        "-dn",
    ])
    if probe["audio_selector"]:
        command.extend(["-map", f"0:{probe['audio_selector']}"])
    if transcode:
        if video_encoder == _ENCODER_H264_VIDEOTOOLBOX:
            command.extend(
                [
                    "-c:v",
                    _ENCODER_H264_VIDEOTOOLBOX,
                    "-pix_fmt",
                    "yuv420p",
                    "-q:v",
                    "60",
                    "-realtime",
                    "true",
                    "-prio_speed",
                    "true",
                    "-frames_before",
                    "true",
                    "-frames_after",
                    "true",
                ]
            )
        else:
            command.extend(
                [
                    "-c:v",
                    _ENCODER_LIBX264,
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    "-c:a",
                    "aac",
                ]
            )
        if probe["audio_selector"]:
            command.extend(
                [
                    "-b:a",
                    str(int(audio_settings.get("bit_rate", 160000))),
                    "-ar",
                    str(int(audio_settings.get("sample_rate", 48000))),
                    "-ac",
                    str(int(audio_settings.get("channels", 2))),
                ]
            )
    else:
        command.extend(["-c", "copy"])
    command.extend(["-movflags", "+faststart", "-y", str(output)])
    return command


def _export_timeline(
    segments: list[dict[str, Any]],
    assets: dict[str, dict[str, Any]],
    probes: dict[str, dict[str, Any]],
    audio_settings: dict[str, Any],
    video_encoder: str,
    output_dir: Path,
    strategy: str,
) -> tuple[Path | None, str]:
    if not segments:
        return None, _STRATEGY_NONE
    output = output_dir / "highlight-reel.mp4"
    first_probe = probes[segments[0]["source_path"]]
    hwaccel_candidates = (True, False) if _supports_videotoolbox_hwaccel() else (False,)
    if strategy == _STRATEGY_STREAM_COPY:
        list_path = _write_concat_list(segments, output_dir)
        try:
            subprocess.run(
                _concat_command(
                    list_path,
                    output,
                    transcode=False,
                    probe=first_probe,
                    video_encoder=video_encoder,
                    audio_settings=audio_settings,
                ),
                check=True,
            )
            return output, _STRATEGY_STREAM_COPY
        except subprocess.CalledProcessError:
            output.unlink(missing_ok=True)
            strategy = _STRATEGY_SINGLE_TRANSCODE
    if strategy == _STRATEGY_SINGLE_TRANSCODE:
        list_path = _write_concat_list(segments, output_dir)
        for use_hwaccel in hwaccel_candidates:
            try:
                subprocess.run(
                    _concat_command(
                        list_path,
                        output,
                        transcode=True,
                        probe=first_probe,
                        video_encoder=video_encoder,
                        audio_settings=audio_settings,
                        use_hwaccel=use_hwaccel,
                    ),
                    check=True,
                )
                return output, _STRATEGY_SINGLE_TRANSCODE
            except subprocess.CalledProcessError:
                output.unlink(missing_ok=True)
        strategy = _STRATEGY_COMPATIBILITY_TRANSCODE
    if strategy == _STRATEGY_COMPATIBILITY_TRANSCODE:
        for use_hwaccel in hwaccel_candidates:
            try:
                subprocess.run(
                    _compatibility_command(
                        segments, assets, probes, audio_settings, video_encoder, output, use_hwaccel=use_hwaccel
                    ),
                    check=True,
                )
                return output, _STRATEGY_COMPATIBILITY_TRANSCODE
            except subprocess.CalledProcessError:
                output.unlink(missing_ok=True)
    raise ValueError(f"Unsupported export strategy: {strategy}")


def _single_transcode_command(
    segments: list[dict[str, Any]],
    probes: dict[str, dict[str, Any]],
    audio_settings: dict[str, Any],
    video_encoder: str,
    output: Path,
) -> list[str]:
    source_paths = list(dict.fromkeys(segment["source_path"] for segment in segments))
    input_indexes = {path: index for index, path in enumerate(source_paths)}
    filters: list[str] = []
    video_inputs: dict[tuple[str, int], str] = {}
    audio_inputs: dict[tuple[str, int], str] = {}
    has_audio = any(probes[path]["audio"] is not None for path in source_paths)
    uses_by_path: dict[str, list[int]] = {
        path: [index for index, segment in enumerate(segments) if segment["source_path"] == path]
        for path in source_paths
    }
    for path in source_paths:
        source_index = input_indexes[path]
        video_selector = probes[path]["video_selector"]
        audio_selector = probes[path]["audio_selector"]
        uses = uses_by_path[path]
        if len(uses) == 1:
            video_inputs[(path, uses[0])] = f"[{source_index}:{video_selector}]"
            if has_audio and audio_selector:
                audio_inputs[(path, uses[0])] = f"[{source_index}:{audio_selector}]"
            continue
        video_branch_labels = [f"[single-source-v-{source_index}-{offset}]" for offset in range(len(uses))]
        filters.append(f"[{source_index}:{video_selector}]split={len(uses)}{''.join(video_branch_labels)}")
        for segment_index, label in zip(uses, video_branch_labels):
            video_inputs[(path, segment_index)] = label
        if has_audio and audio_selector:
            audio_branch_labels = [f"[single-source-a-{source_index}-{offset}]" for offset in range(len(uses))]
            filters.append(f"[{source_index}:{audio_selector}]asplit={len(uses)}{''.join(audio_branch_labels)}")
            for segment_index, label in zip(uses, audio_branch_labels):
                audio_inputs[(path, segment_index)] = label
    concat_labels: list[str] = []
    video_labels: list[str] = []
    for index, segment in enumerate(segments):
        source_path = segment["source_path"]
        start = float(segment["start"])
        end = float(segment["end"])
        video_label = f"single-v{index}"
        filters.append(
            f"{video_inputs[(source_path, index)]}trim=start={start:.3f}:end={end:.3f},"
            f"setpts=PTS-STARTPTS[{video_label}]"
        )
        video_labels.append(f"[{video_label}]")
        if has_audio:
            audio_label = f"single-a{index}"
            filters.append(
                f"{audio_inputs[(source_path, index)]}atrim=start={start:.3f}:end={end:.3f},"
                f"asetpts=PTS-STARTPTS[{audio_label}]"
            )
            concat_labels.extend([f"[{video_label}]", f"[{audio_label}]"])
        else:
            concat_labels.append(f"[{video_label}]")
    if has_audio:
        filters.append(f"{''.join(concat_labels)}concat=n={len(segments)}:v=1:a=1[outv][outa]")
    else:
        filters.append(f"{''.join(video_labels)}concat=n={len(segments)}:v=1:a=0[outv]")

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    for path in source_paths:
        command.extend(["-i", path])
    command.extend(["-filter_complex", ";".join(filters), "-map", "[outv]"])
    if has_audio:
        command.extend(["-map", "[outa]"])
    if video_encoder == _ENCODER_H264_VIDEOTOOLBOX:
        command.extend(["-c:v", _ENCODER_H264_VIDEOTOOLBOX, "-pix_fmt", "yuv420p", "-q:v", "60"])
    else:
        command.extend(["-c:v", _ENCODER_LIBX264, "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"])
    if has_audio:
        command.extend([
            "-c:a",
            "aac",
            "-b:a",
            str(int(audio_settings.get("bit_rate", 160000))),
            "-ar",
            str(int(audio_settings.get("sample_rate", 48000))),
            "-ac",
            str(int(audio_settings.get("channels", 2))),
        ])
    command.extend(["-movflags", "+faststart", "-y", str(output)])
    return command


def _compatibility_command(
    segments: list[dict[str, Any]],
    assets: dict[str, dict[str, Any]],
    probes: dict[str, dict[str, Any]],
    audio_settings: dict[str, Any],
    video_encoder: str,
    output: Path,
    use_hwaccel: bool = False,
) -> list[str]:
    source_paths = list(dict.fromkeys(segment["source_path"] for segment in segments))
    first_video = probes[source_paths[0]]["video"]
    target_width = int(first_video[4] or assets[segments[0]["asset_id"]].get("width") or 1280)
    target_height = int(first_video[5] or assets[segments[0]["asset_id"]].get("height") or 720)
    target_width -= target_width % 2
    target_height -= target_height % 2
    input_indexes = {path: index for index, path in enumerate(source_paths)}
    filters: list[str] = []
    video_labels: list[str] = []
    audio_labels: list[str] = []
    concat_labels: list[str] = []
    has_audio = any(probes[path]["audio"] is not None for path in source_paths)
    uses_by_path: dict[str, list[int]] = {
        path: [index for index, segment in enumerate(segments) if segment["source_path"] == path]
        for path in source_paths
    }
    video_inputs: dict[tuple[str, int], str] = {}
    audio_inputs: dict[tuple[str, int], str] = {}
    input_prefix = ["-hwaccel", "videotoolbox"] if use_hwaccel and _supports_videotoolbox_hwaccel() else []
    for path in source_paths:
        source_index = input_indexes[path]
        video_selector = probes[path]["video_selector"]
        audio_selector = probes[path]["audio_selector"]
        uses = uses_by_path[path]
        if len(uses) == 1:
            video_inputs[(path, uses[0])] = f"[{source_index}:{video_selector}]"
            if has_audio and audio_selector:
                audio_inputs[(path, uses[0])] = f"[{source_index}:{audio_selector}]"
            continue
        video_branch_labels = [f"[source-v-{source_index}-{offset}]" for offset in range(len(uses))]
        filters.append(
            f"[{source_index}:{video_selector}]split={len(uses)}{''.join(video_branch_labels)}"
        )
        for segment_index, label in zip(uses, video_branch_labels):
            video_inputs[(path, segment_index)] = label
        if has_audio and audio_selector:
            audio_branch_labels = [f"[source-a-{source_index}-{offset}]" for offset in range(len(uses))]
            filters.append(
                f"[{source_index}:{audio_selector}]asplit={len(uses)}{''.join(audio_branch_labels)}"
            )
            for segment_index, label in zip(uses, audio_branch_labels):
                audio_inputs[(path, segment_index)] = label
    for index, segment in enumerate(segments):
        source_path = segment["source_path"]
        start = float(segment["start"])
        end = float(segment["end"])
        duration = end - start
        video_label = f"v{index}"
        filters.append(
            f"{video_inputs[(source_path, index)]}trim=start={start:.3f}:end={end:.3f},"
            f"setpts=PTS-STARTPTS,scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,setsar=1[{video_label}]"
        )
        video_labels.append(f"[{video_label}]")
        if has_audio:
            audio_label = f"a{index}"
            if probes[source_path]["audio"] is not None:
                filters.append(
                    f"{audio_inputs[(source_path, index)]}atrim=start={start:.3f}:end={end:.3f},"
                    f"asetpts=PTS-STARTPTS,aresample={int(audio_settings.get('sample_rate', 48000))},"
                    f"aformat=sample_fmts=fltp:channel_layouts={audio_settings.get('channel_layout', 'stereo')}[{audio_label}]"
                )
            else:
                filters.append(
                    f"anullsrc=r={int(audio_settings.get('sample_rate', 48000))}:cl={audio_settings.get('channel_layout', 'stereo')},"
                    f"atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[{audio_label}]"
                )
            audio_labels.append(f"[{audio_label}]")
            concat_labels.extend([f"[{video_label}]", f"[{audio_label}]"])
        else:
            concat_labels.append(f"[{video_label}]")
    if has_audio:
        concat_inputs = "".join(concat_labels)
        filters.append(f"{concat_inputs}concat=n={len(segments)}:v=1:a=1[outv][outa]")
    else:
        filters.append(f"{''.join(video_labels)}concat=n={len(segments)}:v=1:a=0[outv]")

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    for path in source_paths:
        command.extend(input_prefix)
        command.extend(["-i", path])
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[outv]",
        ]
    )
    if has_audio:
        command.extend(["-map", "[outa]"])
    if video_encoder == _ENCODER_H264_VIDEOTOOLBOX:
        command.extend(["-c:v", _ENCODER_H264_VIDEOTOOLBOX, "-pix_fmt", "yuv420p", "-q:v", "60"])
    else:
        command.extend(["-c:v", _ENCODER_LIBX264, "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"])
    if has_audio:
        command.extend([
            "-c:a",
            "aac",
            "-b:a",
            str(int(audio_settings.get("bit_rate", 160000))),
            "-ar",
            str(int(audio_settings.get("sample_rate", 48000))),
            "-ac",
            str(int(audio_settings.get("channels", 2))),
        ])
    command.extend(["-movflags", "+faststart", "-y", str(output)])
    return command


def _write_fcpxml(
    path: Path,
    segments: list[dict[str, Any]],
    assets: dict[str, dict[str, Any]],
) -> None:
    fcpxml = Element("fcpxml", version="1.10")
    resources = SubElement(fcpxml, "resources")
    format_node = SubElement(resources, "format", id="r-format", name="PromptClip-Skill")
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
    event = SubElement(library, "event", name="PromptClip-Skill")
    project = SubElement(event, "project", name="PromptClip-Skill")
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

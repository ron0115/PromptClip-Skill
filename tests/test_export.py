import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from video_highlight.export import _single_transcode_command, default_export_dir, export_run


class ExportTests(unittest.TestCase):
    def test_single_transcode_adds_videotoolbox_before_each_input(self):
        segments = [
            {"source_path": "/tmp/a.mp4", "start": 0.3, "end": 0.8},
            {"source_path": "/tmp/b.mp4", "start": 1.0, "end": 1.5},
        ]
        probes = {
            "/tmp/a.mp4": {"video_selector": "v:0", "audio_selector": None, "audio": None},
            "/tmp/b.mp4": {"video_selector": "v:0", "audio_selector": None, "audio": None},
        }

        with patch("video_highlight.export._supports_videotoolbox_hwaccel", return_value=True):
            command = _single_transcode_command(
                segments,
                probes,
                {},
                "h264_videotoolbox",
                Path("/tmp/output.mp4"),
                use_hwaccel=True,
            )

        self.assertEqual(command.count("-hwaccel"), 2)
        for index, value in enumerate(command):
            if value == "-hwaccel":
                self.assertEqual(command[index + 1], "videotoolbox")
                self.assertEqual(command[index + 2], "-i")

    def test_default_export_dir_uses_input_media_folder(self):
        run = {
            "run_id": "run-default-output",
            "assets": [
                {"path": "/tmp/source-material/a.mp4"},
                {"path": "/tmp/source-material/b.mp4"},
            ],
        }

        self.assertEqual(
            default_export_dir(run),
            Path("/tmp/source-material").resolve() / "PromptClip-Highlights" / "run-default-output",
        )

    def make_source(
        self,
        path: Path,
        color: str,
        size: str = "160x90",
        duration: float = 1.0,
        gop: int = 10,
        with_audio: bool = True,
        audio_bitrate: str | None = None,
        audio_source: str = "silence",
    ) -> None:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={size}:r=10:d={duration}",
        ]
        if with_audio:
            audio_input = (
                "anullsrc=channel_layout=stereo:sample_rate=48000"
                if audio_source == "silence"
                else "sine=frequency=1000:sample_rate=48000"
            )
            command.extend([
                "-f",
                "lavfi",
                "-i",
                audio_input,
                "-shortest",
            ])
        command.extend([
            "-c:v",
            "libx264",
            "-g",
            str(gop),
        ])
        if with_audio:
            command.extend(["-c:a", "aac"])
            if audio_bitrate is not None:
                command.extend(["-b:a", audio_bitrate])
        command.extend(["-y", str(path)])
        subprocess.run(command, check=True)

    def make_source_with_preview(self, path: Path) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=160x90:r=10:d=1",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=64x36:r=10:d=1",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-map",
                "1:v:0",
                "-map",
                "0:v:0",
                "-map",
                "2:a:0",
                "-shortest",
                "-c:v:0",
                "mjpeg",
                "-c:v:1",
                "libx264",
                "-g",
                "10",
                "-c:a",
                "aac",
                "-metadata:s:v:0",
                "handler_name=DJI Preview",
                "-metadata:s:v:1",
                "handler_name=VideoHandler",
                "-y",
                str(path),
            ],
            check=True,
        )

    def test_export_creates_one_merged_mp4_for_multiple_segments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_a = root / "a.mp4"
            source_b = root / "b.mp4"
            self.make_source(source_a, "red")
            self.make_source(source_b, "blue")
            run = {
                "run_id": "run-export",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset-a", "path": str(source_a), "duration": 1.0, "has_audio": True},
                    {"asset_id": "asset-b", "path": str(source_b), "duration": 1.0, "has_audio": True},
                ],
                "candidates": [
                    {"candidate_id": "candidate-a", "asset_id": "asset-a", "start": 0.0, "end": 1.0, "status": "accepted"},
                    {"candidate_id": "candidate-b", "asset_id": "asset-b", "start": 0.0, "end": 1.0, "status": "accepted"},
                ],
            }

            manifest = export_run(run, root / "export")

            merged = Path(manifest["merged_path"])
            self.assertTrue(merged.exists())
            self.assertEqual(len(manifest["segments"]), 2)
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(merged)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertGreater(float(json.loads(probe.stdout)["format"]["duration"]), 1.5)

            self.assertEqual(manifest["export_strategy"], "stream_copy")
            self.assertTrue(manifest["source_preserved"])
            self.assertFalse(manifest["reencoded"])
            self.assertEqual(
                [path.name for path in (root / "export").glob("*.mp4")],
                ["highlight-reel.mp4"],
            )

    def test_platform_profile_transcodes_to_upload_friendly_h264(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "red", duration=1.0)
            run = {
                "run_id": "run-platform",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 1.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.0, "end": 1.0, "status": "accepted"},
                ],
            }

            manifest = export_run(run, root / "export", export_profile="platform")

            self.assertEqual(manifest["export_profile"], "platform")
            self.assertEqual(manifest["export_strategy"], "single_transcode")
            self.assertFalse(manifest["source_preserved"])
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name,pix_fmt",
                    "-of",
                    "json",
                    manifest["merged_path"],
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            video = json.loads(probe.stdout)["streams"][0]
            self.assertEqual(video["codec_name"], "h264")
            self.assertEqual(video["pix_fmt"], "yuv420p")

    def test_platform_profile_prefers_hardware_encoder_when_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "red", duration=1.0)
            run = {
                "run_id": "run-platform-hw",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 1.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.0, "end": 1.0, "status": "accepted"},
                ],
            }

            manifest = export_run(run, root / "export", export_profile="platform")

            self.assertEqual(manifest["video_encoder"], "h264_videotoolbox")

    def test_platform_profile_prefers_source_audio_bitrate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "red", duration=10.0, audio_bitrate="64k", audio_source="tone")
            run = {
                "run_id": "run-platform-audio",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 10.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.0, "end": 10.0, "status": "accepted"},
                ],
            }

            manifest = export_run(run, root / "export", export_profile="platform")

            self.assertGreaterEqual(manifest["target_audio_bitrate"], 60000)
            self.assertLessEqual(manifest["target_audio_bitrate"], 65000)
            self.assertEqual(manifest["target_audio_sample_rate"], 48000)
            self.assertEqual(manifest["target_audio_channels"], 1)

    def test_unsafe_cut_uses_one_transcode_without_intermediate_clips(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "orange", duration=2.0, gop=10)
            run = {
                "run_id": "run-unsafe-cut",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 2.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.3, "end": 0.8, "status": "accepted"}
                ],
            }

            manifest = export_run(run, root / "export")

            self.assertEqual(manifest["export_strategy"], "single_transcode")
            self.assertFalse(manifest["source_preserved"])
            self.assertTrue(manifest["reencoded"])
            self.assertEqual(
                [path.name for path in (root / "export").glob("*.mp4")],
                ["highlight-reel.mp4"],
            )

    def test_single_transcode_does_not_use_concat_inpoints_for_unsafe_cuts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "orange", duration=2.0, gop=10)
            run = {
                "run_id": "run-filter-transcode",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 2.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.3, "end": 0.8, "status": "accepted"}
                ],
            }

            manifest = export_run(run, root / "export")

            self.assertEqual(manifest["export_strategy"], "single_transcode")
            self.assertEqual(manifest["video_encoder"], "libx264")

    def test_single_transcode_resets_output_timestamps_to_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "orange", duration=3.0, gop=10)
            run = {
                "run_id": "run-reset-timestamps",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 3.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.3, "end": 1.2, "status": "accepted"}
                ],
            }

            manifest = export_run(run, root / "export", export_profile="platform")

            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=start_time:stream=index,codec_type,start_time",
                    "-of",
                    "json",
                    manifest["merged_path"],
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            data = json.loads(probe.stdout)
            self.assertEqual(manifest["export_strategy"], "single_transcode")
            self.assertEqual(data["format"]["start_time"], "0.000000")
            self.assertEqual(data["streams"][0]["start_time"], "0.000000")
            self.assertEqual(data["streams"][1]["start_time"], "0.000000")

    def test_platform_profile_uses_hardware_accelerated_concat_transcode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "orange", duration=2.0, gop=10)
            run = {
                "run_id": "run-platform-concat",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 2.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.3, "end": 0.8, "status": "accepted"}
                ],
            }

            manifest = export_run(run, root / "export", export_profile="platform")

            self.assertEqual(manifest["export_strategy"], "single_transcode")
            self.assertEqual(manifest["video_encoder"], "h264_videotoolbox")
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name,pix_fmt",
                    "-of",
                    "json",
                    manifest["merged_path"],
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            video = json.loads(probe.stdout)["streams"][0]
            self.assertEqual(video["codec_name"], "h264")
            self.assertEqual(video["pix_fmt"], "yuv420p")

    def test_fast_unsafe_cut_snaps_to_keyframes_for_stream_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "orange", duration=2.0, gop=10)
            run = {
                "run_id": "run-fast-snap",
                "prompt": "keep highlights",
                "provider": "agent-storyboard",
                "mode": "fast",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 2.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.3, "end": 0.8, "status": "pending"}
                ],
            }

            manifest = export_run(run, root / "export", include_pending=True, mode="fast")

            self.assertEqual(manifest["export_strategy"], "stream_copy")
            self.assertTrue(manifest["source_preserved"])
            self.assertFalse(manifest["reencoded"])
            self.assertEqual(manifest["segments"][0]["requested_start"], 0.3)
            self.assertEqual(manifest["segments"][0]["requested_end"], 0.8)
            self.assertEqual(manifest["segments"][0]["start"], 0.0)
            self.assertAlmostEqual(manifest["segments"][0]["end"], 1.0, places=3)

    def test_near_keyframe_cut_is_not_treated_as_keyframe_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "orange", duration=2.0, gop=10)
            run = {
                "run_id": "run-near-keyframe",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 2.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.05, "end": 0.95, "status": "accepted"}
                ],
            }

            manifest = export_run(run, root / "export")

            self.assertEqual(manifest["export_strategy"], "single_transcode")

    def test_legacy_no_transcode_flag_still_checks_cut_safety(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "orange", duration=2.0, gop=10)
            run = {
                "run_id": "run-legacy-no-transcode",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 2.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.3, "end": 0.8, "status": "accepted"}
                ],
            }

            manifest = export_run(run, root / "export", transcode=False)

            self.assertEqual(manifest["export_strategy"], "single_transcode")

    def test_ignores_dji_preview_video_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source-with-preview.mp4"
            self.make_source_with_preview(source)
            run = {
                "run_id": "run-preview-stream",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 1.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.0, "end": 1.0, "status": "accepted"}
                ],
            }

            manifest = export_run(run, root / "export")
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height,codec_name",
                    "-of",
                    "json",
                    manifest["merged_path"],
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            video = json.loads(probe.stdout)["streams"][0]
            self.assertEqual((video["width"], video["height"]), (160, 90))
            self.assertEqual(video["codec_name"], "h264")

    def test_incompatible_sources_use_compatibility_transcode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_a = root / "a.mp4"
            source_b = root / "b.mp4"
            self.make_source(source_a, "red", size="160x90")
            self.make_source(source_b, "blue", size="128x72")
            run = {
                "run_id": "run-incompatible",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset-a", "path": str(source_a), "duration": 1.0, "has_audio": True},
                    {"asset_id": "asset-b", "path": str(source_b), "duration": 1.0, "has_audio": True},
                ],
                "candidates": [
                    {"candidate_id": "candidate-a", "asset_id": "asset-a", "start": 0.0, "end": 1.0, "status": "accepted"},
                    {"candidate_id": "candidate-b", "asset_id": "asset-b", "start": 0.0, "end": 1.0, "status": "accepted"},
                ],
            }

            manifest = export_run(run, root / "export")

            self.assertEqual(manifest["export_strategy"], "compatibility_transcode")
            self.assertFalse(manifest["source_preserved"])
            self.assertTrue(manifest["reencoded"])
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name,width,height",
                    "-of",
                    "json",
                    manifest["merged_path"],
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            video = json.loads(probe.stdout)["streams"][0]
            self.assertEqual(video["codec_name"], "h264")
            self.assertEqual((video["width"], video["height"]), (160, 90))

    def test_compatibility_transcode_adds_silence_for_missing_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_with_audio = root / "with-audio.mp4"
            source_without_audio = root / "without-audio.mp4"
            self.make_source(source_with_audio, "red", with_audio=True)
            self.make_source(source_without_audio, "blue", with_audio=False)
            run = {
                "run_id": "run-mixed-audio",
                "prompt": "keep highlights",
                "provider": "agent",
                "assets": [
                    {"asset_id": "asset-a", "path": str(source_with_audio), "duration": 1.0, "has_audio": True},
                    {"asset_id": "asset-b", "path": str(source_without_audio), "duration": 1.0, "has_audio": False},
                ],
                "candidates": [
                    {"candidate_id": "candidate-a", "asset_id": "asset-a", "start": 0.0, "end": 1.0, "status": "accepted"},
                    {"candidate_id": "candidate-b", "asset_id": "asset-b", "start": 0.0, "end": 1.0, "status": "accepted"},
                ],
            }

            manifest = export_run(run, root / "export")

            self.assertEqual(manifest["export_strategy"], "compatibility_transcode")
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,codec_name,channels",
                    "-of",
                    "json",
                    manifest["merged_path"],
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            streams = json.loads(probe.stdout)["streams"]
            self.assertEqual([stream["codec_type"] for stream in streams], ["video", "audio"])
            self.assertEqual(streams[1]["codec_name"], "aac")

    def test_fast_mode_exports_pending_candidates_and_records_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "green")
            run = {
                "run_id": "run-fast",
                "prompt": "find highlights",
                "provider": "agent-storyboard",
                "quality_mode": "fast",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 1.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.0, "end": 1.0, "status": "pending"}
                ],
            }

            manifest = export_run(run, root / "export", include_pending=True, mode="fast")

            self.assertEqual(manifest["mode"], "fast")
            self.assertEqual(len(manifest["segments"]), 1)
            report = json.loads((root / "export" / "run-report.json").read_text())
            self.assertEqual(report["mode"], "fast")

    def test_pending_flag_preserves_legacy_fast_export_without_explicit_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "purple")
            run = {
                "run_id": "run-legacy-fast",
                "prompt": "find highlights",
                "provider": "agent",
                "quality_mode": "precise",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 1.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.0, "end": 1.0, "status": "pending"}
                ],
            }

            manifest = export_run(run, root / "export", include_pending=True)

            self.assertEqual(manifest["mode"], "fast")

    def test_precise_mode_rejects_pending_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            self.make_source(source, "yellow")
            run = {
                "run_id": "run-precise",
                "prompt": "precise highlights",
                "provider": "agent-storyboard",
                "quality_mode": "precise",
                "assets": [
                    {"asset_id": "asset", "path": str(source), "duration": 1.0, "has_audio": True}
                ],
                "candidates": [
                    {"candidate_id": "candidate", "asset_id": "asset", "start": 0.0, "end": 1.0, "status": "pending"}
                ],
            }

            with self.assertRaisesRegex(ValueError, "Precise mode requires accepted candidates"):
                export_run(run, root / "export", include_pending=True, mode="precise")


if __name__ == "__main__":
    unittest.main()

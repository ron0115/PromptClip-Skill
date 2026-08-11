import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from video_highlight.export import export_run


class ExportTests(unittest.TestCase):
    def make_source(self, path: Path, color: str) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=160x90:r=10:d=1",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-shortest",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
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

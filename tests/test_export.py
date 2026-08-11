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


if __name__ == "__main__":
    unittest.main()

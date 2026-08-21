import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_highlight.analysis import analyze_run
from video_highlight.models import Asset, Sample, Window, to_jsonable
from video_highlight.storage import save_run


class AnalyzeRunTests(unittest.TestCase):
    def test_analysis_persists_json_shaped_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            asset = Asset(
                asset_id="asset-1",
                path="/tmp/example.mp4",
                sha256="hash",
                size_bytes=10,
                duration=8.0,
                width=640,
                height=360,
                fps=24.0,
                video_codec="h264",
                audio_codec="aac",
                has_audio=True,
            )
            sample = Sample("sample-1", "asset-1", 0.0, "/tmp/sample.jpg")
            window = Window("window-1", "asset-1", 0.0, 4.0, ["sample-1"])
            save_run(
                run_dir,
                {
                    "run_id": "run-1",
                    "settings": {
                        "padding_seconds": 1.0,
                        "merge_gap_seconds": 0.5,
                        "minimum_segment_seconds": 2.0,
                    },
                    "assets": [to_jsonable(asset)],
                    "samples": [to_jsonable(sample)],
                    "windows": [to_jsonable(window)],
                    "candidates": [],
                },
            )

            result = analyze_run(run_dir, "keep a clear complete action", "mock")

            self.assertIsInstance(result["candidates"], list)
            reloaded = json.loads((run_dir / "run.json").read_text())
            self.assertIsInstance(reloaded["candidates"], list)

    def test_analysis_includes_enabled_prompt_presets(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            asset = Asset(
                asset_id="asset-1",
                path="/tmp/example.mp4",
                sha256="hash",
                size_bytes=10,
                duration=8.0,
                width=640,
                height=360,
                fps=24.0,
                video_codec="h264",
                audio_codec="aac",
                has_audio=True,
            )
            sample = Sample("sample-1", "asset-1", 0.0, "/tmp/sample.jpg")
            window = Window("window-1", "asset-1", 0.0, 4.0, ["sample-1"])
            save_run(
                run_dir,
                {
                    "run_id": "run-1",
                    "settings": {
                        "padding_seconds": 1.0,
                        "merge_gap_seconds": 0.5,
                        "minimum_segment_seconds": 2.0,
                    },
                    "assets": [to_jsonable(asset)],
                    "samples": [to_jsonable(sample)],
                    "windows": [to_jsonable(window)],
                    "candidates": [],
                },
            )

            result = analyze_run(run_dir, "keep a clear complete action", "mock")

            self.assertIn("leading-obstruction-trim", result["analysis_prompt"])
            self.assertEqual([item["preset_id"] for item in result["prompt_presets"]], ["leading-obstruction-trim"])

    def test_analysis_can_disable_prompt_presets(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            asset = Asset(
                asset_id="asset-1",
                path="/tmp/example.mp4",
                sha256="hash",
                size_bytes=10,
                duration=8.0,
                width=640,
                height=360,
                fps=24.0,
                video_codec="h264",
                audio_codec="aac",
                has_audio=True,
            )
            sample = Sample("sample-1", "asset-1", 0.0, "/tmp/sample.jpg")
            window = Window("window-1", "asset-1", 0.0, 4.0, ["sample-1"])
            save_run(
                run_dir,
                {
                    "run_id": "run-1",
                    "settings": {
                        "padding_seconds": 1.0,
                        "merge_gap_seconds": 0.5,
                        "minimum_segment_seconds": 2.0,
                    },
                    "assets": [to_jsonable(asset)],
                    "samples": [to_jsonable(sample)],
                    "windows": [to_jsonable(window)],
                    "candidates": [],
                },
            )

            with patch.dict("os.environ", {"PROMPTCLIP_DISABLED_PROMPT_PRESETS": "leading-obstruction-trim"}):
                result = analyze_run(run_dir, "keep a clear complete action", "mock")

            self.assertEqual(result["analysis_prompt"], "keep a clear complete action")
            self.assertEqual(result["prompt_presets"], [])


if __name__ == "__main__":
    unittest.main()

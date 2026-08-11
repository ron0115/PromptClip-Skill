import json
import tempfile
import unittest
from pathlib import Path

from video_highlight.agent_pipeline import apply_agent_decisions, apply_storyboard_decisions, build_batches
from video_highlight.models import Asset, Sample, Window, to_jsonable
from video_highlight.storage import load_run, save_json, save_run


class AgentPipelineTests(unittest.TestCase):
    def make_run(self, directory: Path) -> None:
        asset = Asset("asset-1", "/tmp/example.mp4", "hash", 10, 12, 640, 360, 24, "h264", "aac", True)
        samples = [Sample(f"sample-{index}", "asset-1", index * 2.0, f"/tmp/{index}.jpg") for index in range(6)]
        windows = [
            Window("window-1", "asset-1", 0.0, 4.0, ["sample-0", "sample-1"]),
            Window("window-2", "asset-1", 3.0, 7.0, ["sample-1", "sample-2", "sample-3"]),
        ]
        save_run(
            directory,
            {
                "run_id": "run-1",
                "settings": {"padding_seconds": 1.0, "merge_gap_seconds": 0.5, "minimum_segment_seconds": 2.0},
                "assets": [to_jsonable(asset)],
                "samples": [to_jsonable(sample) for sample in samples],
                "windows": [to_jsonable(window) for window in windows],
                "candidates": [],
            },
        )

    def test_builds_batches_with_window_and_frame_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self.make_run(run_dir)

            batches = build_batches(run_dir, batch_size=1)

            self.assertEqual(len(batches), 2)
            self.assertEqual(batches[0]["windows"][0]["window_id"], "window-1")
            self.assertEqual(batches[0]["windows"][0]["sample_ids"], ["sample-0", "sample-1"])

    def test_candidate_batches_persist_deduplicated_refinement_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self.make_run(run_dir)
            run = load_run(run_dir)
            run["candidates"] = [{
                "candidate_id": "candidate-1",
                "asset_id": "asset-1",
                "start": 0.0,
                "end": 10.0,
                "score": 0.8,
                "tags": ["candidate"],
                "reason": "candidate",
                "status": "pending",
                "source_window_ids": [],
            }]
            save_run(run_dir, run)

            batches = build_batches(run_dir, batch_size=8, only_candidates=True)
            windows = [window for batch in batches for window in batch["windows"]]
            persisted = load_run(run_dir)["analysis_windows"]

            self.assertEqual([window["start"] for window in windows], [0.0, 4.0, 8.0])
            self.assertEqual([window["window_id"] for window in windows], [item["window_id"] for item in persisted])

    def test_agent_decisions_use_persisted_candidate_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self.make_run(run_dir)
            run = load_run(run_dir)
            run["candidates"] = [{
                "candidate_id": "candidate-1",
                "asset_id": "asset-1",
                "start": 0.0,
                "end": 10.0,
                "score": 0.8,
                "tags": ["candidate"],
                "reason": "candidate",
                "status": "pending",
                "source_window_ids": [],
            }]
            save_run(run_dir, run)
            build_batches(run_dir, batch_size=8, only_candidates=True)
            analysis_window_id = load_run(run_dir)["analysis_windows"][0]["window_id"]
            decisions_path = run_dir / "decisions.json"
            decisions_path.write_text(
                json.dumps([{
                    "window_id": analysis_window_id,
                    "keep": True,
                    "score": 0.9,
                    "tags": ["clear"],
                    "reason": "candidate window kept",
                }]),
                encoding="utf-8",
            )

            result = apply_agent_decisions(run_dir, "keep clear actions", decisions_path)

            self.assertEqual(result["analysis_window_count"], 3)
            self.assertEqual(result["candidates"][0]["source_window_ids"], [analysis_window_id])

    def test_applies_agent_window_decisions_and_persists_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self.make_run(run_dir)
            decisions_path = run_dir / "decisions.json"
            decisions_path.write_text(
                json.dumps([
                    {"window_id": "window-1", "keep": True, "score": 0.9, "tags": ["clear"], "reason": "complete"},
                    {"window_id": "window-2", "keep": False, "score": 0.1, "tags": ["blur"], "reason": "discard"},
                ]),
                encoding="utf-8",
            )

            result = apply_agent_decisions(run_dir, "keep clear actions", decisions_path)

            self.assertEqual(result["provider"], "agent")
            self.assertEqual(result["analysis_mode"], "frames")
            self.assertEqual(len(result["candidates"]), 1)
            self.assertEqual(result["candidates"][0]["status"], "pending")

    def test_applies_storyboard_cell_decisions_as_coarse_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self.make_run(run_dir)
            save_json(
                run_dir / "storyboards.json",
                [
                    {
                        "storyboard_id": "asset-1-minute-0000",
                        "asset_id": "asset-1",
                        "minute_index": 0,
                        "start": 0.0,
                        "end": 7.0,
                        "cells": [
                            {"cell_index": 0, "sample_id": "sample-0", "timestamp": 0.0, "path": "/tmp/0.jpg"},
                            {"cell_index": 1, "sample_id": "sample-1", "timestamp": 2.0, "path": "/tmp/1.jpg"},
                        ],
                    }
                ],
            )
            decisions_path = run_dir / "storyboard-decisions.json"
            decisions_path.write_text(
                json.dumps([{"storyboard_id": "asset-1-minute-0000", "keep_cells": [1], "score": 0.8, "tags": ["event"], "reason": "visible"}]),
                encoding="utf-8",
            )

            result = apply_storyboard_decisions(run_dir, "keep visible events", decisions_path)

            self.assertEqual(result["analysis_mode"], "storyboard")
            self.assertEqual(result["quality_mode"], "fast")
            self.assertEqual(len(result["candidates"]), 1)
            self.assertEqual(result["candidates"][0]["start"], 0.5)

    def test_applies_detail_storyboard_decisions_from_detail_specs(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self.make_run(run_dir)
            save_json(
                run_dir / "detail-storyboards.json",
                [{
                    "storyboard_id": "asset-1-detail-0000",
                    "asset_id": "asset-1",
                    "detail_start": 0.0,
                    "start": 0.0,
                    "end": 7.0,
                    "cells": [{
                        "cell_index": 0,
                        "sample_id": "sample-0",
                        "timestamp": 0.0,
                        "path": "/tmp/0.jpg",
                    }],
                }],
            )
            decisions_path = run_dir / "detail-decisions.json"
            decisions_path.write_text(
                json.dumps([{
                    "storyboard_id": "asset-1-detail-0000",
                    "keep_cells": [0],
                    "score": 0.8,
                    "tags": ["event"],
                    "reason": "visible face",
                }]),
                encoding="utf-8",
            )

            result = apply_storyboard_decisions(
                run_dir,
                "keep visible faces",
                decisions_path,
                mode="precise",
            )

            self.assertEqual(result["analysis_mode"], "detail-storyboard")
            self.assertEqual(result["quality_mode"], "precise")
            self.assertEqual(len(result["candidates"]), 1)

    def test_can_merge_storyboard_rescue_candidates_with_existing_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self.make_run(run_dir)
            run = load_run(run_dir)
            run["candidates"] = [{
                "candidate_id": "existing",
                "asset_id": "asset-1",
                "start": 6.0,
                "end": 9.0,
                "score": 0.7,
                "tags": ["existing"],
                "reason": "existing candidate",
                "status": "pending",
                "source_window_ids": ["window-2"],
            }]
            save_run(run_dir, run)
            save_json(
                run_dir / "storyboards.json",
                [{
                    "storyboard_id": "asset-1-detail-0000",
                    "asset_id": "asset-1",
                    "minute_index": 0,
                    "start": 0.0,
                    "end": 7.0,
                    "cells": [{"cell_index": 0, "sample_id": "sample-0", "timestamp": 0.0, "path": "/tmp/0.jpg"}],
                }],
            )
            decisions_path = run_dir / "storyboard-decisions.json"
            decisions_path.write_text(
                json.dumps([{"storyboard_id": "asset-1-detail-0000", "keep_cells": [0], "score": 0.8, "tags": ["rescue"], "reason": "rescue hit"}]),
                encoding="utf-8",
            )

            result = apply_storyboard_decisions(
                run_dir,
                "rescue",
                decisions_path,
                merge_existing=True,
            )

            self.assertEqual(len(result["candidates"]), 2)


if __name__ == "__main__":
    unittest.main()

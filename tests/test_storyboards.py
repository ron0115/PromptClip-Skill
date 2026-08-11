import unittest

from video_highlight.models import Sample
from video_highlight.storyboards import make_detail_storyboard_specs, make_storyboard_specs


class StoryboardTests(unittest.TestCase):
    def test_groups_one_second_samples_into_sixty_cell_minutes(self):
        samples = [Sample(f"sample-{i}", "asset-1", float(i), f"/tmp/{i}.jpg") for i in range(125)]

        specs = make_storyboard_specs(samples, cells_per_board=60)

        self.assertEqual(len(specs), 3)
        self.assertEqual(len(specs[0]["cells"]), 60)
        self.assertEqual(specs[0]["cells"][0]["timestamp"], 0.0)
        self.assertEqual(specs[0]["cells"][-1]["timestamp"], 59.0)
        self.assertEqual(len(specs[2]["cells"]), 5)

    def test_keeps_asset_boundaries_when_sample_timestamps_restart(self):
        samples = [
            Sample("a-0", "asset-a", 0.0, "/tmp/a0.jpg"),
            Sample("a-1", "asset-a", 1.0, "/tmp/a1.jpg"),
            Sample("b-0", "asset-b", 0.0, "/tmp/b0.jpg"),
        ]

        specs = make_storyboard_specs(samples, cells_per_board=60)

        self.assertEqual([spec["asset_id"] for spec in specs], ["asset-a", "asset-b"])

    def test_detail_storyboards_use_larger_twelve_cell_rescue_boards(self):
        samples = [Sample(f"sample-{i}", "asset-1", float(i), f"/tmp/{i:06d}.jpg") for i in range(65)]

        specs = make_detail_storyboard_specs(samples, seconds_per_board=30, cells_per_board=12)

        self.assertEqual(len(specs), 3)
        self.assertEqual(len(specs[0]["cells"]), 12)
        self.assertEqual(specs[0]["cells"][0]["timestamp"], 0.0)
        self.assertEqual(specs[0]["cells"][-1]["timestamp"], 27.0)
        self.assertEqual(len(specs[2]["cells"]), 5)

    def test_detail_storyboards_can_limit_coverage_to_prefilter_positive_blocks(self):
        samples = [Sample(f"sample-{i}", "asset-1", float(i), f"/tmp/{i:06d}.jpg") for i in range(65)]

        specs = make_detail_storyboard_specs(
            samples,
            seconds_per_board=30,
            cells_per_board=12,
            active_sample_ids={"sample-1", "sample-40"},
        )

        self.assertEqual([spec["detail_start"] for spec in specs], [0.0, 30.0])
        self.assertTrue(all(
            spec["start"] <= cell["timestamp"] < spec["end"]
            for spec in specs
            for cell in spec["cells"]
        ))
        self.assertTrue(all(
            cell["sample_id"] in {"sample-1", "sample-40"}
            for spec in specs
            for cell in spec["cells"]
        ))


if __name__ == "__main__":
    unittest.main()

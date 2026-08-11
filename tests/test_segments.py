import unittest

from video_highlight.models import Sample
from video_highlight.segments import Candidate, build_candidate_windows, merge_candidates


class MergeCandidatesTests(unittest.TestCase):
    def test_build_candidate_windows_tiles_candidate_ranges_without_overlap(self):
        samples = [Sample(f"sample-{i}", "asset-1", float(i), f"/tmp/{i}.jpg") for i in range(13)]
        candidates = [Candidate("candidate", "asset-1", 1.0, 11.0, 0.8, [], "reason")]

        windows = build_candidate_windows(samples, candidates, window_seconds=4.0)

        self.assertEqual([(window.start, window.end) for window in windows], [(1.0, 5.0), (5.0, 9.0), (9.0, 13.0)])
        self.assertEqual(len({window.window_id for window in windows}), 3)

    def test_merges_overlapping_candidates_and_adds_bounded_padding(self):
        candidates = [
            Candidate("a", "asset-1", 10.0, 14.0, 0.8, ["first"], "reason"),
            Candidate("b", "asset-1", 13.0, 20.0, 0.9, ["second"], "reason"),
        ]

        merged = merge_candidates(
            candidates,
            asset_duration=25.0,
            padding=1.0,
            merge_gap=0.5,
            minimum_duration=2.0,
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual((merged[0].start, merged[0].end), (9.0, 21.0))
        self.assertEqual(merged[0].tags, ["first", "second"])
        self.assertEqual(merged[0].status, "pending")

    def test_clamps_padding_to_asset_boundaries_and_discards_tiny_segments(self):
        candidates = [
            Candidate("a", "asset-1", 0.2, 0.8, 0.8, [], "reason"),
            Candidate("b", "asset-1", 8.0, 10.0, 0.8, [], "reason"),
        ]

        merged = merge_candidates(
            candidates,
            asset_duration=10.0,
            padding=1.0,
            merge_gap=0.5,
            minimum_duration=2.0,
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual((merged[0].start, merged[0].end), (7.0, 10.0))


if __name__ == "__main__":
    unittest.main()

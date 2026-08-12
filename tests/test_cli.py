import unittest

from video_highlight.cli import build_parser


class CliTests(unittest.TestCase):
    def test_storyboard_apply_accepts_auto_fast_and_precise_modes(self):
        parser = build_parser()

        args = parser.parse_args([
            "apply-storyboard-decisions",
            "--run", "run",
            "--prompt", "find highlights",
            "--decisions", "decisions.json",
            "--mode", "precise",
        ])

        self.assertEqual(args.mode, "precise")

    def test_export_accepts_a_final_mode(self):
        parser = build_parser()

        args = parser.parse_args([
            "export",
            "--run", "run",
            "--output", "export",
            "--mode", "fast",
            "--include-pending",
        ])

        self.assertEqual(args.mode, "fast")
        self.assertTrue(args.include_pending)

    def test_export_output_is_optional(self):
        parser = build_parser()

        args = parser.parse_args([
            "export",
            "--run", "run",
            "--mode", "fast",
            "--include-pending",
        ])

        self.assertIsNone(args.output)

    def test_export_defaults_to_platform_profile(self):
        parser = build_parser()

        args = parser.parse_args([
            "export",
            "--run", "run",
            "--mode", "fast",
            "--include-pending",
        ])

        self.assertEqual(args.profile, "platform")


if __name__ == "__main__":
    unittest.main()

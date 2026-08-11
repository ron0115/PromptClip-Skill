import unittest

from video_highlight.modes import resolve_mode


class ModeTests(unittest.TestCase):
    def test_defaults_to_fast_for_a_normal_highlight_prompt(self):
        self.assertEqual(resolve_mode("找出宝宝最精彩的片段"), "fast")

    def test_switches_to_precise_for_explicit_precision_requirements(self):
        self.assertEqual(resolve_mode("精剪并保证切点精准"), "precise")
        self.assertEqual(resolve_mode("精确切点"), "precise")
        self.assertEqual(resolve_mode("每一帧都必须有宝宝的脸"), "precise")

    def test_explicit_mode_overrides_prompt_detection(self):
        self.assertEqual(resolve_mode("精剪并保证切点精准", requested="fast"), "fast")

    def test_rejects_unknown_mode(self):
        with self.assertRaisesRegex(ValueError, "Mode must be auto, fast, or precise"):
            resolve_mode("找出精彩片段", requested="balanced")


if __name__ == "__main__":
    unittest.main()

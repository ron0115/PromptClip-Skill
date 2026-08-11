import unittest
from pathlib import Path

from video_highlight.prefilter import (
    build_face_detector_command,
    is_face_prompt,
)


class FacePrefilterTests(unittest.TestCase):
    def test_recognizes_positive_face_requirements(self):
        self.assertTrue(is_face_prompt("每一帧必须要有宝宝的脸出现"))
        self.assertTrue(is_face_prompt("keep shots where the face is visible"))
        self.assertTrue(is_face_prompt("保留人脸清晰的片段"))

    def test_does_not_activate_for_unrelated_semantic_prompts(self):
        self.assertFalse(is_face_prompt("保留风景变化明显、画面稳定的片段"))

    def test_builds_one_apple_vision_batch_command(self):
        command = build_face_detector_command(
            Path("/tmp/apple-face-detector.swift"),
            [Path("/tmp/a.jpg"), Path("/tmp/b.jpg")],
        )

        self.assertEqual(command[:2], ["swift", "/tmp/apple-face-detector.swift"])
        self.assertEqual(command[2:], ["/tmp/a.jpg", "/tmp/b.jpg"])


if __name__ == "__main__":
    unittest.main()

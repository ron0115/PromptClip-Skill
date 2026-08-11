import unittest
from pathlib import Path

from video_highlight.media import build_sample_command, resolve_hwaccel
from video_highlight.models import Asset


class MediaCommandTests(unittest.TestCase):
    def make_asset(self) -> Asset:
        return Asset(
            asset_id="asset-1",
            path="/tmp/input.mp4",
            sha256="hash",
            size_bytes=10,
            duration=10.0,
            width=2688,
            height=1512,
            fps=30.0,
            video_codec="hevc",
            audio_codec="aac",
            has_audio=True,
        )

    def test_sample_command_places_videotoolbox_before_input(self):
        command = build_sample_command(
            self.make_asset(),
            Path("/tmp/frames/%06d.jpg"),
            interval=1.0,
            width=640,
            hwaccel="videotoolbox",
        )

        self.assertEqual(command[command.index("-hwaccel") + 1], "videotoolbox")
        self.assertLess(command.index("-hwaccel"), command.index("-i"))

    def test_sample_command_omits_hardware_flag_when_disabled(self):
        command = build_sample_command(
            self.make_asset(),
            Path("/tmp/frames/%06d.jpg"),
            interval=1.0,
            width=640,
            hwaccel=None,
        )

        self.assertNotIn("-hwaccel", command)

    def test_auto_hardware_acceleration_is_platform_specific(self):
        self.assertEqual(resolve_hwaccel("auto", platform="darwin"), "videotoolbox")
        self.assertIsNone(resolve_hwaccel("auto", platform="linux"))
        self.assertIsNone(resolve_hwaccel("none", platform="darwin"))


if __name__ == "__main__":
    unittest.main()

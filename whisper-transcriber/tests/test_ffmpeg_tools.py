from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from app.ffmpeg_tools import media_duration_sec


class FfmpegToolsTests(unittest.TestCase):
    def test_media_duration_parses_ffmpeg_stderr(self) -> None:
        stderr = "Input #0\n  Duration: 01:02:03.50, start: 0.000000\n"
        with mock.patch("app.ffmpeg_tools.subprocess.run") as run:
            run.return_value = mock.Mock(stderr=stderr, stdout="", returncode=1)
            seconds = media_duration_sec(Path("clip.mp4"), ffmpeg="/usr/bin/ffmpeg")
        self.assertAlmostEqual(seconds, 3723.5)


if __name__ == "__main__":
    unittest.main()

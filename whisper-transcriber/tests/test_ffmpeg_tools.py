from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from app.ffmpeg_tools import has_audio_stream, media_duration_sec, summarize_ffmpeg_error


class FfmpegToolsTests(unittest.TestCase):
    def test_media_duration_parses_ffmpeg_stderr(self) -> None:
        stderr = "Input #0\n  Duration: 01:02:03.50, start: 0.000000\n"
        with mock.patch("app.ffmpeg_tools.subprocess.run") as run:
            run.return_value = mock.Mock(stderr=stderr, stdout="", returncode=1)
            seconds = media_duration_sec(Path("clip.mp4"), ffmpeg="/usr/bin/ffmpeg")
        self.assertAlmostEqual(seconds, 3723.5)

    def test_has_audio_stream_true_and_false(self) -> None:
        with_audio = (
            "Stream #0:0: Video: h264\n"
            "Stream #0:1(und): Audio: aac, 48000 Hz, stereo\n"
        )
        # Типичный вывод macOS/QuickTime с [0xN]
        with_audio_bracket = (
            "Stream #0:0[0x1](und): Video: h264 (Main) (avc1 / 0x31637661)\n"
            "Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, stereo\n"
        )
        video_only = "Stream #0:0[0x1](und): Video: h264 (Main) (avc1 / 0x31637661)\n"
        with mock.patch("app.ffmpeg_tools.subprocess.run") as run:
            run.return_value = mock.Mock(stderr=with_audio, stdout="", returncode=1)
            self.assertTrue(has_audio_stream(Path("a.mov"), ffmpeg="/usr/bin/ffmpeg"))
            run.return_value = mock.Mock(stderr=with_audio_bracket, stdout="", returncode=1)
            self.assertTrue(has_audio_stream(Path("b.mov"), ffmpeg="/usr/bin/ffmpeg"))
            run.return_value = mock.Mock(stderr=video_only, stdout="", returncode=1)
            self.assertFalse(has_audio_stream(Path("v.mov"), ffmpeg="/usr/bin/ffmpeg"))

    def test_summarize_keeps_error_lines(self) -> None:
        text = "ffmpeg version 9\nconfiguration: --foo\nOutput file #0 does not contain any stream\n"
        summary = summarize_ffmpeg_error(text)
        self.assertIn("does not contain any stream", summary)
        self.assertNotIn("configuration", summary)


if __name__ == "__main__":
    unittest.main()

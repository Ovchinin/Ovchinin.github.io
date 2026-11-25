from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from app.ffmpeg_tools import (
    count_audio_streams,
    has_audio_stream,
    media_duration_sec,
    summarize_ffmpeg_error,
    wav_rms_level,
)


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

    def test_count_audio_streams_phone_screen_recording(self) -> None:
        # Запись экрана телефона: видео + одна или две аудидорожки
        dual = (
            "Stream #0:0[0x1](eng): Video: h264\n"
            "Stream #0:1[0x2](eng): Audio: aac, 44100 Hz, mono\n"
            "Stream #0:2[0x3](eng): Audio: aac, 48000 Hz, stereo\n"
        )
        with mock.patch("app.ffmpeg_tools.subprocess.run") as run:
            run.return_value = mock.Mock(stderr=dual, stdout="", returncode=1)
            self.assertEqual(count_audio_streams(Path("phone.mp4"), ffmpeg="/usr/bin/ffmpeg"), 2)

    def test_wav_rms_level_quiet_vs_loud(self) -> None:
        import array
        import tempfile
        import wave

        def _write(path: Path, amp: int) -> None:
            with wave.open(str(path), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                samples = array.array("h", [amp if i % 2 == 0 else -amp for i in range(8000)])
                wf.writeframes(samples.tobytes())

        with tempfile.TemporaryDirectory() as tmp:
            quiet = Path(tmp) / "quiet.wav"
            loud = Path(tmp) / "loud.wav"
            _write(quiet, 50)
            _write(loud, 8000)
            self.assertLess(wav_rms_level(quiet), 0.01)
            self.assertGreater(wav_rms_level(loud), 0.1)

    def test_summarize_keeps_error_lines(self) -> None:
        text = "ffmpeg version 9\nconfiguration: --foo\nOutput file #0 does not contain any stream\n"
        summary = summarize_ffmpeg_error(text)
        self.assertIn("does not contain any stream", summary)
        self.assertNotIn("configuration", summary)


if __name__ == "__main__":
    unittest.main()

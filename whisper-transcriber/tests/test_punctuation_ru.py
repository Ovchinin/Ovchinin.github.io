from __future__ import annotations

import unittest

from app.punctuation_ru import format_russian_transcript, segments_to_plain_text, segments_to_srt


class PunctuationRuTests(unittest.TestCase):
    def test_spaces_and_capitals(self) -> None:
        raw = "привет ,как дела?всё хорошо.мы идём дальше"
        out = format_russian_transcript(raw, paragraph_breaks=False)
        self.assertIn("Привет,", out)
        self.assertIn("как дела?", out)
        self.assertIn("Всё хорошо.", out)
        self.assertRegex(out, r"\?\s+Всё")
        self.assertRegex(out, r"\.\s+Мы")

    def test_segments_paragraphs_by_pause(self) -> None:
        segments = [
            {"start": 0.0, "end": 1.0, "text": "Первая фраза."},
            {"start": 1.1, "end": 2.0, "text": "Вторая фраза."},
            {"start": 5.0, "end": 6.0, "text": "Новый абзац."},
        ]
        text = segments_to_plain_text(segments, paragraph_gap_sec=1.4)
        self.assertIn("\n\n", text)
        self.assertTrue(text.startswith("Первая"))

    def test_srt_has_punctuation(self) -> None:
        srt = segments_to_srt([{"start": 0, "end": 1.5, "text": "привет мир"}])
        self.assertIn("-->", srt)
        self.assertIn("Привет мир", srt)


if __name__ == "__main__":
    unittest.main()
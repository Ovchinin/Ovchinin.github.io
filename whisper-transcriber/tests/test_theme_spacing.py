from __future__ import annotations

import unittest

from app.theme import letter_spaced, unletter_spaced


class LetterSpacingTests(unittest.TestCase):
    def test_roundtrip_model_label(self) -> None:
        raw = "small — ~500 МБ, ≈ 1.5 мин"
        spaced = letter_spaced(raw)
        self.assertIn("\u2009", spaced)
        self.assertEqual(unletter_spaced(spaced), raw)

    def test_preserves_spaces(self) -> None:
        spaced = letter_spaced("А Б")
        self.assertTrue(spaced.startswith("А"))
        self.assertIn(" ", spaced)
        self.assertEqual(unletter_spaced(spaced), "А Б")


if __name__ == "__main__":
    unittest.main()

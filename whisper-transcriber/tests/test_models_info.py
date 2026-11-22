from __future__ import annotations

import unittest

from app.models_info import download_status_message, format_size_gb, get_model_info, model_download_hint


class ModelsInfoTests(unittest.TestCase):
    def test_medium_size_and_eta(self) -> None:
        info = get_model_info("medium")
        self.assertAlmostEqual(info.size_gb, 1.5)
        self.assertGreaterEqual(info.avg_download_min, 3)
        self.assertIn("ГБ", format_size_gb(info.size_gb))

    def test_hint_and_status_include_size(self) -> None:
        hint = model_download_hint("medium")
        self.assertIn("medium", hint)
        self.assertIn("ГБ", hint)
        self.assertIn("мин", hint)
        status = download_status_message("medium", 150)
        self.assertIn("150", status)
        self.assertIn("ГБ", status)


if __name__ == "__main__":
    unittest.main()

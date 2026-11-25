from __future__ import annotations

import unittest

from app.models_info import (
    MODEL_ORDER,
    all_models_legend,
    download_status_message,
    format_size_gb,
    get_model_info,
    model_download_hint,
    model_label_for_ui,
)


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

    def test_all_models_have_size_labels(self) -> None:
        legend = all_models_legend()
        for name in MODEL_ORDER:
            info = get_model_info(name)
            label = model_label_for_ui(name)
            self.assertIn(format_size_gb(info.size_gb), label)
            self.assertIn(name, legend)
            self.assertIn(format_size_gb(info.size_gb), legend)


if __name__ == "__main__":
    unittest.main()

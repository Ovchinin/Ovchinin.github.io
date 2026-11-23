from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.export import render_export, write_export


class ExportTests(unittest.TestCase):
    def test_txt_and_md_keep_text(self) -> None:
        sample = "Привет, мир.\nВторая строка"
        self.assertIn("Привет", render_export(sample, ".txt"))
        self.assertIn("Вторая строка", render_export(sample, ".md"))

    def test_rtf_and_html_escape(self) -> None:
        sample = "A & B <C>"
        rtf = render_export(sample, ".rtf")
        self.assertTrue(rtf.startswith("{\\rtf1"))
        html = render_export(sample, ".html")
        self.assertIn("&amp;", html)
        self.assertIn("&lt;C&gt;", html)

    def test_write_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.txt"
            write_export(path, "Текст")
            self.assertTrue(path.exists())
            self.assertIn("Текст", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

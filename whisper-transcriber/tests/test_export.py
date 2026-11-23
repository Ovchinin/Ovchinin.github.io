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

    def test_doc_word_html(self) -> None:
        doc = render_export("Привет & мир", ".doc")
        self.assertIsInstance(doc, str)
        self.assertIn("w:WordDocument", doc)
        self.assertIn("Привет", doc)
        self.assertIn("&amp;", doc)

    def test_pdf_bytes_with_cyrillic(self) -> None:
        pdf = render_export("Привет, мир.\nВторая строка", ".pdf")
        self.assertIsInstance(pdf, (bytes, bytearray))
        self.assertTrue(bytes(pdf).startswith(b"%PDF"))

    def test_write_export_txt_and_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            txt = Path(tmp) / "out.txt"
            write_export(txt, "Текст")
            self.assertIn("Текст", txt.read_text(encoding="utf-8"))

            pdf = Path(tmp) / "out.pdf"
            write_export(pdf, "Текст PDF")
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))

            doc = Path(tmp) / "out.doc"
            write_export(doc, "Текст DOC")
            self.assertIn("Текст DOC", doc.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

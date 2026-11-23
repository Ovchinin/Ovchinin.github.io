"""Экспорт результата транскрибации в выбранный формат («Сохранить как»)."""

from __future__ import annotations

from pathlib import Path


SAVE_AS_FILETYPES = [
    ("Текстовый файл", "*.txt"),
    ("Markdown", "*.md"),
    ("Документ Word", "*.doc"),
    ("PDF", "*.pdf"),
    ("Rich Text (RTF)", "*.rtf"),
    ("HTML", "*.html"),
]

_EXT_BY_TYPE = {
    "Текстовый файл": ".txt",
    "Markdown": ".md",
    "Документ Word": ".doc",
    "PDF": ".pdf",
    "Rich Text (RTF)": ".rtf",
    "HTML": ".html",
}

_BINARY_EXTS = {".pdf"}


def default_extension_for_dialog(file_type_label: str | None) -> str:
    if not file_type_label:
        return ".txt"
    for key, ext in _EXT_BY_TYPE.items():
        if key in file_type_label:
            return ext
    return ".txt"


def _fonts_dir() -> Path:
    # …/whisper-transcriber/app/export.py → …/resources/fonts
    return Path(__file__).resolve().parent.parent / "resources" / "fonts"


def _unicode_font_path() -> Path:
    bundled = _fonts_dir() / "DejaVuSans.ttf"
    if bundled.is_file():
        return bundled
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError(
        "Не найден шрифт с кириллицей для PDF. "
        "Ожидался resources/fonts/DejaVuSans.ttf в приложении."
    )


def _escape_rtf(text: str) -> str:
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == "{":
            out.append("\\{")
        elif ch == "}":
            out.append("\\}")
        elif ch == "\n":
            out.append("\\par\n")
        elif code < 128:
            out.append(ch)
        else:
            out.append(f"\\u{code}?")
    return "".join(out)


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_doc_word_html(plain: str) -> str:
    """Word HTML — открывается в Word/Pages как .doc, без внешних библиотек."""
    paragraphs = plain.split("\n")
    body = "\n".join(f"<p>{_escape_html(line) if line else '&nbsp;'}</p>" for line in paragraphs)
    return (
        "<html xmlns:o='urn:schemas-microsoft-com:office:office'\n"
        "      xmlns:w='urn:schemas-microsoft-com:office:word'\n"
        "      xmlns='http://www.w3.org/TR/REC-html40'>\n"
        "<head>\n"
        "<meta charset='utf-8'>\n"
        "<title>Транскрибация</title>\n"
        "<!--[if gte mso 9]>\n"
        "<xml>\n"
        " <w:WordDocument>\n"
        "  <w:View>Print</w:View>\n"
        " </w:WordDocument>\n"
        "</xml>\n"
        "<![endif]-->\n"
        "<style>\n"
        " body { font-family: Arial, Helvetica, sans-serif; font-size: 12pt; }\n"
        " p { margin: 0 0 8pt 0; }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def _render_pdf_bytes(plain: str) -> bytes:
    from fpdf import FPDF

    font_path = _unicode_font_path()
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.add_font("DejaVu", fname=str(font_path))
    pdf.set_font("DejaVu", size=12)
    # multi_cell корректно переносит кириллицу
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    for line in plain.split("\n"):
        if not line.strip():
            pdf.ln(6)
            continue
        pdf.multi_cell(usable, 7, line)
    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return str(out).encode("latin-1")


def render_export(text: str, ext: str) -> str | bytes:
    """Содержимое файла: str для текстовых форматов, bytes для PDF."""
    ext = (ext or ".txt").lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    plain = text.replace("\r\n", "\n").replace("\r", "\n")

    if ext == ".md":
        return plain if plain.endswith("\n") else plain + "\n"

    if ext == ".doc":
        return _render_doc_word_html(plain)

    if ext == ".pdf":
        return _render_pdf_bytes(plain)

    if ext == ".rtf":
        body = _escape_rtf(plain)
        return (
            "{\\rtf1\\ansi\\deff0\\uc1\n"
            "{\\fonttbl{\\f0 Helvetica;}}\n"
            "\\f0\\fs24\n"
            f"{body}\n"
            "}\n"
        )

    if ext in {".html", ".htm"}:
        body = "<br>\n".join(_escape_html(line) for line in plain.split("\n"))
        return (
            "<!DOCTYPE html>\n"
            '<html lang="ru">\n'
            "<head>\n"
            '  <meta charset="utf-8">\n'
            "  <title>Транскрибация</title>\n"
            "</head>\n"
            "<body>\n"
            f"<p>{body}</p>\n"
            "</body>\n"
            "</html>\n"
        )

    return plain if plain.endswith("\n") else plain + "\n"


def write_export(path: Path, text: str) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render_export(text, path.suffix)
    if isinstance(content, (bytes, bytearray)):
        path.write_bytes(bytes(content))
    else:
        path.write_text(content, encoding="utf-8")
    return path

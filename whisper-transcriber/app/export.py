"""Экспорт результата транскрибации в выбранный формат («Сохранить как»)."""

from __future__ import annotations

from pathlib import Path


SAVE_AS_FILETYPES = [
    ("Текстовый файл", "*.txt"),
    ("Markdown", "*.md"),
    ("Rich Text (RTF)", "*.rtf"),
    ("HTML", "*.html"),
]

_EXT_BY_TYPE = {
    "Текстовый файл": ".txt",
    "Markdown": ".md",
    "Rich Text (RTF)": ".rtf",
    "HTML": ".html",
}


def default_extension_for_dialog(file_type_label: str | None) -> str:
    if not file_type_label:
        return ".txt"
    for key, ext in _EXT_BY_TYPE.items():
        if key in file_type_label:
            return ext
    return ".txt"


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


def render_export(text: str, ext: str) -> str:
    """Вернуть содержимое файла для расширения (.txt / .md / .rtf / .html)."""
    ext = (ext or ".txt").lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    plain = text.replace("\r\n", "\n").replace("\r", "\n")

    if ext == ".md":
        return plain if plain.endswith("\n") else plain + "\n"

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

    # .txt и всё остальное — простой текст
    return plain if plain.endswith("\n") else plain + "\n"


def write_export(path: Path, text: str) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render_export(text, path.suffix)
    path.write_text(content, encoding="utf-8")
    return path

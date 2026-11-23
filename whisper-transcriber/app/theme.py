"""Минималистичная палитра и типографика «Транскрибация»."""

from __future__ import annotations

import customtkinter as ctk

# Холодная бумага / чернила — без фиолетового и «cream + terracotta»
COLOR = {
    "bg": ("#F3F4F6", "#141414"),
    "surface": ("#FFFFFF", "#1C1C1C"),
    "muted_surface": ("#ECEDEF", "#222222"),
    "ink": ("#141414", "#F2F2F2"),
    "muted": ("#6B7280", "#9CA3AF"),
    "faint": ("#9CA3AF", "#6B7280"),
    "line": ("#E5E7EB", "#2A2A2A"),
    "accent": ("#1F3A34", "#A7C4BC"),  # приглушённый хвойный, только для CTA
    "accent_hover": ("#16302B", "#B9D4CC"),
    "progress": ("#1F3A34", "#A7C4BC"),
    "progress_track": ("#E5E7EB", "#2A2A2A"),
    "entry_border": ("#D1D5DB", "#333333"),
}

PRIMARY_BTN = {
    "fg_color": COLOR["accent"],
    "hover_color": COLOR["accent_hover"],
    "text_color": ("#F8FAF9", "#0E1614"),
    "text_color_disabled": ("#A8B5B1", "#5A6B66"),
    "corner_radius": 6,
    "border_width": 0,
}

SECONDARY_BTN = {
    # Лёгкая заливка + обводка: в disabled текст остаётся читаемым
    "fg_color": COLOR["surface"],
    "hover_color": COLOR["muted_surface"],
    "text_color": COLOR["ink"],
    "text_color_disabled": ("#4B5563", "#A3A3A3"),
    "border_width": 1,
    "border_color": COLOR["line"],
    "corner_radius": 6,
}

GHOST_BTN = {
    "fg_color": "transparent",
    "hover_color": COLOR["muted_surface"],
    "text_color": COLOR["muted"],
    "text_color_disabled": COLOR["faint"],
    "border_width": 0,
    "corner_radius": 4,
}

_FONT_FAMILY: str | None = None


def font_family() -> str:
    """Выразительный гротеск; без Inter/Roboto/Arial/system."""
    global _FONT_FAMILY
    if _FONT_FAMILY:
        return _FONT_FAMILY

    preferred = (
        "Avenir Next",
        "Avenir",
        "Futura",
        "Gill Sans",
        "Helvetica Neue",
        "DejaVu Sans",
    )
    try:
        import tkinter as tk
        from tkinter import font as tkfont

        root = getattr(tk, "_default_root", None)
        created = False
        if root is None:
            root = tk.Tk()
            root.withdraw()
            created = True
        names = {n.lower(): n for n in tkfont.families(root)}
        if created:
            root.destroy()
        for name in preferred:
            if name.lower() in names:
                _FONT_FAMILY = names[name.lower()]
                return _FONT_FAMILY
    except Exception:
        pass
    _FONT_FAMILY = "Helvetica Neue"
    return _FONT_FAMILY


def F(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=font_family(), size=size, weight=weight)


def apply_appearance() -> None:
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

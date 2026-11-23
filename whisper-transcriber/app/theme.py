"""Editorial-минимализм: тёплый камень, уголь, гротеск без засечек."""

from __future__ import annotations

import customtkinter as ctk

# Тёплый камень / уголь — без фиолетового; акцент угольный, не terracotta
COLOR = {
    "bg": ("#E8E6E1", "#161513"),
    "surface": ("#F7F6F3", "#1E1C1A"),
    "muted_surface": ("#DDDAD3", "#2A2825"),
    "ink": ("#1A1917", "#F3F1EC"),
    "muted": ("#6F6A62", "#A39E94"),
    "faint": ("#958F85", "#7A756C"),
    "line": ("#D2CEC5", "#33302C"),
    "accent": ("#2A2825", "#E8E4DC"),
    "accent_hover": ("#1A1917", "#F3F1EC"),
    "progress": ("#2A2825", "#C9C3B8"),
    "progress_track": ("#D2CEC5", "#33302C"),
    "entry_border": ("#C8C3B8", "#3A3732"),
}

PRIMARY_BTN = {
    "fg_color": COLOR["accent"],
    "hover_color": COLOR["accent_hover"],
    "text_color": ("#F7F6F3", "#1A1917"),
    "text_color_disabled": ("#9A958C", "#5C584F"),
    "corner_radius": 8,
    "border_width": 0,
}

SECONDARY_BTN = {
    "fg_color": COLOR["surface"],
    "hover_color": COLOR["muted_surface"],
    "text_color": COLOR["ink"],
    "text_color_disabled": ("#6F6A62", "#A39E94"),
    "border_width": 1,
    "border_color": COLOR["line"],
    "corner_radius": 8,
}

GHOST_BTN = {
    "fg_color": "transparent",
    "hover_color": COLOR["muted_surface"],
    "text_color": COLOR["muted"],
    "text_color_disabled": COLOR["faint"],
    "border_width": 0,
    "corner_radius": 6,
}

_FONT_FAMILY: str | None = None


def font_family() -> str:
    """Гротеск без засечек: Gill Sans (стандарт macOS), затем запасные."""
    global _FONT_FAMILY
    if _FONT_FAMILY:
        return _FONT_FAMILY

    preferred = (
        "Gill Sans",
        "Gill Sans MT",
        "GillSans",
        "Futura",
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

#!/usr/bin/env python3
"""Двухцветная иконка: видео → текст."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

BG = (21, 32, 24, 255)
FG = (216, 240, 224, 255)
ROOT = Path(__file__).resolve().parent


def make_icon(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 1024.0

    def u(v: float) -> int:
        return int(round(v * s))

    draw.rounded_rectangle([u(64), u(64), u(960), u(960)], radius=u(220), fill=BG)

    # Video
    draw.rounded_rectangle([u(190), u(340), u(420), u(684)], radius=u(48), fill=FG)
    draw.rounded_rectangle([u(238), u(396), u(372), u(628)], radius=u(28), fill=BG)
    draw.polygon([(u(278), u(430)), (u(278), u(594)), (u(368), u(512))], fill=FG)

    # Arrow
    draw.rectangle([u(448), u(480), u(560), u(544)], fill=FG)
    draw.polygon([(u(548), u(420)), (u(548), u(604)), (u(660), u(512))], fill=FG)

    # Text doc
    draw.rounded_rectangle([u(690), u(300), u(880), u(724)], radius=u(44), fill=FG)
    draw.polygon([(u(790), u(300)), (u(880), u(300)), (u(880), u(390))], fill=BG)
    draw.polygon([(u(790), u(300)), (u(790), u(390)), (u(880), u(390))], fill=FG)
    for i, y in enumerate([430, 500, 570, 640]):
        x2 = 810 if i == 3 else 840
        draw.rounded_rectangle([u(730), u(y), u(x2), u(y + 28)], radius=u(10), fill=BG)

    return img


def main() -> None:
    master = make_icon(1024)
    master.save(ROOT / "AppIcon-1024.png")
    for s in (16, 32, 64, 128, 256, 512, 1024):
        master.resize((s, s), Image.Resampling.LANCZOS).save(ROOT / f"AppIcon-{s}.png")
    print(f"Wrote icons to {ROOT}")


if __name__ == "__main__":
    main()
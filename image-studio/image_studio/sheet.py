"""Contact sheets for reviewing a set side by side (optionally before/after)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .imgio import open_image


def contact_sheet(items: list[tuple[str, list[Path | Image.Image]]], tile: int = 360, columns: int | None = None) -> Image.Image:
    """items: [(label, [image, image, ...]), ...] - each item's images sit next to each other."""
    per = max(len(imgs) for _, imgs in items)
    columns = columns or max(1, 6 // per)
    label_h = 24
    rows = -(-len(items) // columns)
    gap = 12
    sheet = Image.new("RGB", (columns * (per * tile + gap), rows * (tile + label_h + gap)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=14)
    for i, (label, imgs) in enumerate(items):
        x = (i % columns) * (per * tile + gap)
        y = (i // columns) * (tile + label_h + gap)
        draw.text((x + 4, y + 4), label, fill="black", font=font)
        for j, src in enumerate(imgs):
            im = src if isinstance(src, Image.Image) else open_image(src)
            im = ImageOps.contain(im, (tile, tile))
            sheet.paste(im, (x + j * tile + (tile - im.width) // 2, y + label_h + (tile - im.height) // 2))
    return sheet

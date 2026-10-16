"""Regenerates the site-wide background texture (frontend/public/patterns/
henna-bg.svg) as a denser, more authentic-looking mehndi motif tile -
flowers, paisleys and a connecting vine, instead of the original sparse
dot-and-paisley placeholder.

Run from repo root: backend/venv/Scripts/python.exe scripts/generate_background.py
"""

import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "frontend", "public", "patterns", "henna-bg.svg")

MAROON = "#5C1A21"
GOLD = "#A9761E"
CREAM = "#F3EAD9"

TILE = 240
PAISLEY_D = "M12 2C7 2 3 6 3 11c0 3 2 5 4 6-1 1-2 3-2 5 0 3 2 5 5 5 6 0 11-5 11-12C21 6 17 2 12 2z"


def paisley(cx, cy, scale, angle_deg, color=GOLD):
    return (
        f'<g transform="translate({cx},{cy}) rotate({angle_deg}) scale({scale}) translate(-12,-12)" fill="{color}">'
        f'<path d="{PAISLEY_D}"/><circle cx="9" cy="9" r="1.8" fill="{CREAM}"/></g>'
    )


def flower(cx, cy, r, petals, color):
    parts = [f'<g fill="{color}">']
    for i in range(petals):
        ang = 360 * i / petals
        px = cx + r * 0.6 * math.cos(math.radians(ang))
        py = cy + r * 0.6 * math.sin(math.radians(ang))
        parts.append(
            f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="{r*0.4:.1f}" ry="{r*0.2:.1f}" '
            f'transform="rotate({ang:.0f} {px:.1f} {py:.1f})"/>'
        )
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r*0.26:.1f}" fill="{GOLD}"/>')
    parts.append("</g>")
    return "".join(parts)


def dotted_vine(p0, p1, n=10, r=1.4, color=GOLD):
    pts = []
    for i in range(n + 1):
        t = i / n
        x = p0[0] + (p1[0] - p0[0]) * t + 10 * math.sin(t * math.pi * 2)
        y = p0[1] + (p1[1] - p0[1]) * t
        pts.append((x, y))
    return "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}"/>' for x, y in pts)


parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {TILE} {TILE}" width="{TILE}" height="{TILE}">']
parts.append('<g opacity="0.4">')

# two anchor motifs, diagonally placed so the tile repeats without an
# obvious seam - a flower top-left, a paisley bottom-right
parts.append(flower(38, 34, 20, 6, MAROON))
parts.append(paisley(178, 176, 1.3, 150, MAROON))

# smaller accents in the remaining corners
parts.append(paisley(196, 30, 1.0, -20, GOLD))
parts.append(flower(40, 196, 14, 5, GOLD))

# dotted vine trailing between the two anchor motifs
parts.append(dotted_vine((58, 46), (158, 160), n=9, color=GOLD))

# scattered fine dots for texture
for x, y, r in [(110, 90, 1.6), (130, 60, 1.3), (70, 130, 1.3), (150, 110, 1.5), (100, 190, 1.3), (210, 100, 1.4)]:
    parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{MAROON}"/>')

parts.append("</g>")
parts.append("</svg>")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(parts))
print("wrote", OUT)

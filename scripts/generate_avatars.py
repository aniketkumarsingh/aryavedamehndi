"""Generates 6 preset "mehndi medallion" avatars customers can pick instead
of uploading their own photo - circular badges with a distinct henna-style
motif each, in the brand's palette.

Run from repo root: backend/venv/Scripts/python.exe scripts/generate_avatars.py
"""

import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "frontend", "public", "avatars")
os.makedirs(OUT_DIR, exist_ok=True)

MAROON = "#5C1A21"
GOLD = "#A9761E"
GOLD_LIGHT = "#D9A34E"
LEAF = "#4E5F3B"
CREAM = "#FBF6EC"
IVORY = "#F3EAD9"

SIZE = 200
C = SIZE / 2
PAISLEY_D = "M12 2C7 2 3 6 3 11c0 3 2 5 4 6-1 1-2 3-2 5 0 3 2 5 5 5 6 0 11-5 11-12C21 6 17 2 12 2z"


def paisley(cx, cy, scale, angle, color, dot=CREAM):
    return (
        f'<g transform="translate({cx},{cy}) rotate({angle}) scale({scale}) translate(-12,-12)" fill="{color}">'
        f'<path d="{PAISLEY_D}"/><circle cx="9" cy="9" r="1.8" fill="{dot}"/></g>'
    )


def flower(cx, cy, r, petals, color, center=GOLD):
    parts = [f'<g fill="{color}">']
    for i in range(petals):
        a = 360 * i / petals
        px, py = cx + r * 0.6 * math.cos(math.radians(a)), cy + r * 0.6 * math.sin(math.radians(a))
        parts.append(
            f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="{r*0.4:.1f}" ry="{r*0.2:.1f}" '
            f'transform="rotate({a:.0f} {px:.1f} {py:.1f})"/>'
        )
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r*0.26:.1f}" fill="{center}"/>')
    parts.append("</g>")
    return "".join(parts)


def petal_ring(cx, cy, radius, rx, ry, n, color, opacity=1):
    parts = [f'<g fill="{color}" fill-opacity="{opacity}">']
    for i in range(n):
        a = 360 * i / n
        x = cx + radius * math.sin(math.radians(a))
        y = cy - radius * math.cos(math.radians(a))
        parts.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx}" ry="{ry}" transform="rotate({a:.0f} {x:.1f} {y:.1f})"/>')
    parts.append("</g>")
    return "".join(parts)


def dot_ring(cx, cy, radius, n, r, color):
    pts = []
    for i in range(n):
        a = 360 * i / n
        x = cx + radius * math.sin(math.radians(a))
        y = cy - radius * math.cos(math.radians(a))
        pts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}"/>')
    return "".join(pts)


def spiral_path(cx, cy, start_r, end_r, turns, n=48, start_angle=0):
    pts = []
    for i in range(n + 1):
        t = i / n
        r = start_r + (end_r - start_r) * t
        a = start_angle + 360 * turns * t
        pts.append((cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))))
    d = f"M {pts[0][0]:.1f},{pts[0][1]:.1f} " + " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts[1:])
    return d


def wrap(body, bg):
    ring = (
        f'<circle cx="{C}" cy="{C}" r="{C-3}" fill="{bg}"/>'
        f'<circle cx="{C}" cy="{C}" r="{C-3}" fill="none" stroke="{GOLD_LIGHT}" stroke-width="3"/>'
        f'<circle cx="{C}" cy="{C}" r="{C-9}" fill="none" stroke="{GOLD}" stroke-width="1" stroke-opacity="0.6"/>'
    )
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}">{ring}{body}</svg>'


def save(name, svg):
    with open(os.path.join(OUT_DIR, f"{name}.svg"), "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote", name)


# preset-1: Lotus - maroon ground, layered gold/cream flower
body = flower(C, C, 46, 10, MAROON, center=GOLD) + flower(C, C, 28, 8, GOLD_LIGHT, center=MAROON) + flower(C, C, 13, 6, MAROON, center=CREAM)
save("preset-1", wrap(body, IVORY))

# preset-2: Mandala - gold ground, maroon petal ring + dot ring
body = petal_ring(C, C, 55, 9, 26, 12, MAROON, 0.9) + dot_ring(C, C, 34, 12, 3, GOLD) + f'<circle cx="{C}" cy="{C}" r="14" fill="{MAROON}"/><circle cx="{C}" cy="{C}" r="6" fill="{CREAM}"/>'
save("preset-2", wrap(body, "#F3E2C4"))

# preset-3: Paisley Pair - cream ground, two big paisleys mirrored
body = paisley(C - 18, C - 6, 3.2, -20, MAROON) + paisley(C + 18, C + 6, 3.2, 160, GOLD)
save("preset-3", wrap(body, CREAM))

# preset-4: Garden - leaf ground, gold flower + scattered dots
body = flower(C, C, 40, 8, GOLD, center=MAROON) + dot_ring(C, C, 62, 16, 2.4, GOLD_LIGHT)
save("preset-4", wrap(body, "#5B6B4D"))

# preset-5: Spiral - maroon ground, big gold spiral + center dot
body = f'<path d="{spiral_path(C, C, 4, 56, 2.6, 60, 10)}" fill="none" stroke="{GOLD_LIGHT}" stroke-width="4" stroke-linecap="round"/>' + f'<circle cx="{C}" cy="{C}" r="5" fill="{CREAM}"/>'
save("preset-5", wrap(body, MAROON))

# preset-6: Bloom - gold-light ground, mixed maroon+leaf petals
body = petal_ring(C, C, 48, 8, 22, 10, MAROON, 0.85) + flower(C, C, 22, 6, LEAF, center=GOLD)
save("preset-6", wrap(body, "#EADFC3"))

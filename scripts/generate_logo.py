"""Generates the AryaVeda Mehndi logo (two hands - one being decorated with
mehndi, one applying it with a cone) as both a scalable SVG mark and
rasterized PNG app icons, from one shared set of coordinates so the SVG
and the PNG icons always match.

Run:  venv/Scripts/python.exe ../scripts/generate_logo.py   (from backend/)
or:   backend/venv/Scripts/python.exe scripts/generate_logo.py   (from repo root)
"""

import math
import os

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover - Pillow is in backend/venv
    Image = None

HERE = os.path.dirname(os.path.abspath(__file__))
FRONTEND_PUBLIC = os.path.join(HERE, "..", "frontend", "public")

# ---- palette -----------------------------------------------------------
MAROON = "#5C1A21"
GOLD = "#A9761E"
GOLD_LIGHT = "#D9A34E"
CREAM = "#FBF6EC"
INK = "#3A1015"

CANVAS = 400
CENTER = (200, 200)


# ---- geometry helpers ----------------------------------------------------
def rotate(x, y, angle_deg):
    rad = math.radians(angle_deg)
    return (x * math.cos(rad) - y * math.sin(rad), x * math.sin(rad) + y * math.cos(rad))


def capsule(base_x, base_y, length, width, angle_deg, n=14):
    """A finger: one rounded end at (base_x, base_y), extending `length`
    outward along angle_deg, rounded tip at the far end."""
    half_w = width / 2
    pts_local = []
    # base cap (flat-ish, slightly rounded) centered at local (0,0)
    for i in range(n + 1):
        a = 90 + 180 * i / n
        pts_local.append((half_w * math.cos(math.radians(a)), half_w * math.sin(math.radians(a))))
    # tip cap centered at local (length, 0)
    for i in range(n + 1):
        a = -90 + 180 * i / n
        pts_local.append((length + half_w * math.cos(math.radians(a)), half_w * math.sin(math.radians(a))))
    pts = []
    for x, y in pts_local:
        rx, ry = rotate(x, y, angle_deg)
        pts.append((base_x + rx, base_y + ry))
    return pts


def ellipse_poly(cx, cy, rx, ry, angle_deg, n=56):
    pts = []
    for i in range(n):
        a = 360 * i / n
        x = rx * math.cos(math.radians(a))
        y = ry * math.sin(math.radians(a))
        rxp, ryp = rotate(x, y, angle_deg)
        pts.append((cx + rxp, cy + ryp))
    return pts


def unit(angle_deg):
    rad = math.radians(angle_deg)
    return math.cos(rad), math.sin(rad)


def quad_bezier(p0, p1, p2, n=28):
    pts = []
    for i in range(n + 1):
        t = i / n
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
        pts.append((x, y))
    return pts


def spiral(cx, cy, start_r, end_r, turns, n=48, start_angle=0):
    pts = []
    for i in range(n + 1):
        t = i / n
        r = start_r + (end_r - start_r) * t
        a = start_angle + 360 * turns * t
        x = cx + r * math.cos(math.radians(a))
        y = cy + r * math.sin(math.radians(a))
        pts.append((x, y))
    return pts


# ---- Hand A: receiving hand, palm up, lower-left ------------------------
PALM_A = (152, 258)
palm_a = ellipse_poly(PALM_A[0], PALM_A[1], 56, 66, 12)

# (angle_deg, length, width) fanned upward, base attach point offset from palm center
finger_defs_a = [
    ("pinky", -132, 52, 20),
    ("ring", -111, 72, 22),
    ("middle", -92, 80, 23),
    ("index", -73, 72, 21),
]
fingers_a = []
finger_tip_dots = []
for name, ang, length, width in finger_defs_a:
    ux, uy = unit(ang)
    base = (PALM_A[0] + ux * 46, PALM_A[1] + uy * 52)
    fingers_a.append(capsule(base[0], base[1], length, width, ang))
    finger_tip_dots.append((base[0] + ux * length, base[1] + uy * length))

# thumb: shorter, splays out to the lower-left side of the palm
thumb_ang = -18
tux, tuy = unit(thumb_ang)
thumb_base = (PALM_A[0] + tux * 30 - 18, PALM_A[1] + tuy * 10 + 30)
thumb_a = capsule(thumb_base[0], thumb_base[1], 54, 25, thumb_ang - 15)

hand_a_polys = [palm_a] + fingers_a + [thumb_a]

# ---- Hand B: applying hand holding the cone, upper-right ----------------
BLOB_B = (292, 122)
palm_b = ellipse_poly(BLOB_B[0], BLOB_B[1], 40, 46, 35)

finger_defs_b = [
    (-165, 46, 18),
    (-150, 52, 19),
    (-135, 48, 18),
]
fingers_b = []
for ang, length, width in finger_defs_b:
    ux, uy = unit(ang)
    base = (BLOB_B[0] + ux * 22, BLOB_B[1] + uy * 26)
    fingers_b.append(capsule(base[0], base[1], length, width, ang))

# thumb opposes the fingers, pinching the cone from the other side - reads
# as an actual grip rather than a second bundle of fingers.
thumb_b_ang = 55
tbx, tby = unit(thumb_b_ang)
thumb_b_base = (BLOB_B[0] + tbx * 14 - 6, BLOB_B[1] + tby * 14 - 10)
thumb_b = capsule(thumb_b_base[0], thumb_b_base[1], 38, 20, thumb_b_ang)

hand_b_polys = [palm_b] + fingers_b + [thumb_b]

# ---- henna cone -----------------------------------------------------------
CONE_BASE = (262, 108)
CONE_TIP = (178, 202)
dx, dy = CONE_TIP[0] - CONE_BASE[0], CONE_TIP[1] - CONE_BASE[1]
cone_len = math.hypot(dx, dy)
cone_angle = math.degrees(math.atan2(dy, dx))
perp = cone_angle + 90
pux, puy = unit(perp)
base_half_w = 15
tip_half_w = 2.2
cone_poly = [
    (CONE_BASE[0] + pux * base_half_w, CONE_BASE[1] + puy * base_half_w),
    (CONE_TIP[0] + pux * tip_half_w, CONE_TIP[1] + puy * tip_half_w),
    (CONE_TIP[0] - pux * tip_half_w, CONE_TIP[1] - puy * tip_half_w),
    (CONE_BASE[0] - pux * base_half_w, CONE_BASE[1] - puy * base_half_w),
]

# ---- mehndi trail + palm swirl -------------------------------------------
trail_control = ((CONE_TIP[0] + PALM_A[0]) / 2 - 10, (CONE_TIP[1] + PALM_A[1]) / 2 + 6)
swirl_center = (PALM_A[0] - 6, PALM_A[1] - 8)
trail = quad_bezier(CONE_TIP, trail_control, swirl_center, n=24)
palm_swirl = spiral(swirl_center[0], swirl_center[1], 3, 17, 2.3, n=48, start_angle=20)


# ============================================================ SVG output
def fmt_pts(pts):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def svg_polyline_path(pts):
    d = f"M {pts[0][0]:.1f},{pts[0][1]:.1f} "
    d += " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts[1:])
    return d


def build_svg():
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS} {CANVAS}" width="{CANVAS}" height="{CANVAS}">']

    parts.append(f'<circle cx="{CENTER[0]}" cy="{CENTER[1]}" r="188" fill="{MAROON}"/>')
    parts.append(
        f'<circle cx="{CENTER[0]}" cy="{CENTER[1]}" r="181" fill="none" stroke="{GOLD_LIGHT}" stroke-width="4"/>'
    )
    parts.append(
        f'<circle cx="{CENTER[0]}" cy="{CENTER[1]}" r="171" fill="none" stroke="{GOLD}" stroke-width="1.4" stroke-opacity="0.7"/>'
    )

    parts.append(f'<g fill="{CREAM}">')
    for poly in hand_b_polys:
        parts.append(f'<polygon points="{fmt_pts(poly)}"/>')
    parts.append("</g>")

    parts.append(f'<polygon points="{fmt_pts(cone_poly)}" fill="{GOLD_LIGHT}" stroke="{GOLD}" stroke-width="1.5"/>')
    parts.append(
        f'<circle cx="{CONE_TIP[0]:.1f}" cy="{CONE_TIP[1]:.1f}" r="3.4" fill="{INK}"/>'
    )

    parts.append(f'<g fill="{CREAM}">')
    for poly in hand_a_polys:
        parts.append(f'<polygon points="{fmt_pts(poly)}"/>')
    parts.append("</g>")

    parts.append(
        f'<path d="{svg_polyline_path(trail)}" fill="none" stroke="{INK}" stroke-width="2.6" '
        f'stroke-linecap="round"/>'
    )
    parts.append(
        f'<path d="{svg_polyline_path(palm_swirl)}" fill="none" stroke="{INK}" stroke-width="2.4" '
        f'stroke-linecap="round"/>'
    )

    for x, y in finger_tip_dots:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{INK}"/>')

    parts.append("</svg>")
    return "\n".join(parts)


svg_text = build_svg()
os.makedirs(os.path.join(FRONTEND_PUBLIC, "logo"), exist_ok=True)
with open(os.path.join(FRONTEND_PUBLIC, "logo", "mark.svg"), "w", encoding="utf-8") as f:
    f.write(svg_text)
print("wrote logo/mark.svg")


# ============================================================ PNG output
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def render_png(size, path, supersample=4):
    if Image is None:
        print("Pillow not available - skipping PNG render")
        return
    render_medallion(size, supersample).save(path, "PNG")
    print("wrote", path)


def render_padded_icon(size, path, medallion_fraction):
    """The medallion centred on a full-bleed maroon square.

    - Android "maskable" icons get cropped to whatever shape the launcher
      uses (circle, squircle...), and only the centre 80% circle is
      guaranteed visible - so the medallion sits at <= 0.8 of the canvas.
    - iOS apple-touch-icons must be opaque (transparent corners render
      black) and get rounded corners applied by iOS.
    """
    if Image is None:
        return
    canvas = Image.new("RGBA", (size, size), hex_to_rgb(MAROON) + (255,))
    inner = round(size * medallion_fraction)
    medallion = render_medallion(inner)
    offset = (size - inner) // 2
    canvas.alpha_composite(medallion, (offset, offset))
    canvas.convert("RGB").save(path, "PNG")
    print("wrote", path)


def render_medallion(size, supersample=4):
    big = size * supersample
    scale = big / CANVAS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def S(pts):
        return [(x * scale, y * scale) for x, y in pts]

    cx, cy = CENTER[0] * scale, CENTER[1] * scale
    draw.ellipse([cx - 188 * scale, cy - 188 * scale, cx + 188 * scale, cy + 188 * scale], fill=hex_to_rgb(MAROON))
    draw.ellipse(
        [cx - 181 * scale, cy - 181 * scale, cx + 181 * scale, cy + 181 * scale],
        outline=hex_to_rgb(GOLD_LIGHT),
        width=max(1, int(4 * scale)),
    )
    draw.ellipse(
        [cx - 171 * scale, cy - 171 * scale, cx + 171 * scale, cy + 171 * scale],
        outline=hex_to_rgb(GOLD),
        width=max(1, int(1.4 * scale)),
    )

    for poly in hand_b_polys:
        draw.polygon(S(poly), fill=hex_to_rgb(CREAM))

    draw.polygon(S(cone_poly), fill=hex_to_rgb(GOLD_LIGHT), outline=hex_to_rgb(GOLD))
    tx, ty = CONE_TIP[0] * scale, CONE_TIP[1] * scale
    r = 3.4 * scale
    draw.ellipse([tx - r, ty - r, tx + r, ty + r], fill=hex_to_rgb(INK))

    for poly in hand_a_polys:
        draw.polygon(S(poly), fill=hex_to_rgb(CREAM))

    draw.line(S(trail), fill=hex_to_rgb(INK), width=max(1, int(2.6 * scale)), joint="curve")
    draw.line(S(palm_swirl), fill=hex_to_rgb(INK), width=max(1, int(2.4 * scale)), joint="curve")

    for x, y in finger_tip_dots:
        fx, fy = x * scale, y * scale
        fr = 2.6 * scale
        draw.ellipse([fx - fr, fy - fr, fx + fr, fy + fr], fill=hex_to_rgb(INK))

    return img.resize((size, size), Image.LANCZOS)


icons_dir = os.path.join(FRONTEND_PUBLIC, "icons")
os.makedirs(icons_dir, exist_ok=True)
# "any" purpose - shown as-is (transparent corners are fine on desktop).
render_png(192, os.path.join(icons_dir, "icon-192.png"))
render_png(512, os.path.join(icons_dir, "icon-512.png"))
render_png(512, os.path.join(FRONTEND_PUBLIC, "logo", "mark.png"))
# "maskable" purpose - Android launchers crop these to their own shape.
render_padded_icon(192, os.path.join(icons_dir, "maskable-192.png"), 0.78)
render_padded_icon(512, os.path.join(icons_dir, "maskable-512.png"), 0.78)
# iOS home screen icon - opaque, 180x180 is what current iPhones request.
render_padded_icon(180, os.path.join(icons_dir, "apple-touch-icon.png"), 0.88)

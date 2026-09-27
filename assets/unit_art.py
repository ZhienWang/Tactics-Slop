"""Generates the on-map unit art (assets/<name>.png) as refined, anime-style
chibi figures.

Every unit keeps the parts of its original design from print_svg.py - the
isometric stand, the cube head, its hair/beard silhouette, the two-tone open
book and its signature prop - and this only draws them with more care: ink
linework, flat cel shading (lit from the upper left, like the map props),
anime eyes, hair that covers the scalp with bangs, strands and a shine, small
hands holding the book, and detailed props.

All shapes are in the same 64-unit figure space the original master SVG used
(stand centered on x=32, its bottom corner at y=63), and are rendered to a
standard 2:1 canvas so every unit sits at the same size and spot on its tile.

Rendered with PyMuPDF, whose SVG support doesn't do gradients (they come out
black) - hence flat colors throughout.

Run from the project root:  python assets/unit_art.py
"""
import math
import os

import numpy as np
import pymupdf
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))

# Output canvas: 2:1 like the old art (the game squeezes every unit image to
# 2:1), rendered at SUPERSAMPLE times the old pixel size so the detail
# survives the game's zoom.
CANVAS_W, CANVAS_H = 170, 85
SUPERSAMPLE = 2
FIGURE_SCALE = 2.15               # canvas pixels per figure unit
FIGURE_BOTTOM = 64.7              # figure-space y at the canvas's bottom edge
ORIGIN_X = CANVAS_W / 2 - 32 * FIGURE_SCALE
ORIGIN_Y = CANVAS_H - FIGURE_BOTTOM * FIGURE_SCALE

INK = "#2b1a12"
INK_W = 0.28

SKIN = {"base": "#fcd5ae", "shade": "#efb68c", "light": "#ffe4c8", "edge": "#e6a57c"}
BLUSH = "#f39a90"

HAIR = {
    "dark": {"base": "#4a2a14", "shade": "#2c170a", "light": "#9a6a44"},
    "grey": {"base": "#a7b1bf", "shade": "#6f7a8a", "light": "#eef2f7"},
}

# Robe/book colors from the original palette (flat: base, shade, trim).
CLOTH = {
    "blue": ("#38bdf8", "#0369a1"),
    "gold": ("#fde047", "#ca8a04"),
    "green": ("#4ade80", "#15803d"),
    "white": ("#ffffff", "#cbd5e1"),
    "crimson": ("#f87171", "#991b1b"),
    "purple": ("#c084fc", "#6b21a8"),
    "orange": ("#fb923c", "#c2410c"),
    "teal": ("#2dd4bf", "#0f766e"),
    "brown": ("#a16207", "#451a03"),
    "slate": ("#475569", "#1e293b"),
    # Paul's own flat colors (his figure was already hand-flattened).
    "paul_brown": ("#8a4a0c", "#5a2e05"),
    "paul_purple": ("#a864e0", "#6b2fa8"),
}

GOLD = {"base": "#f2c230", "shade": "#b7860b", "light": "#fff1a8"}
STEEL = {"base": "#cbd5e1", "shade": "#7b8797", "light": "#ffffff"}
WOOD = {"base": "#7a4318", "shade": "#4a260a", "light": "#b4733d"}

# Each unit, keyed by its asset filename: which original figure it was drawn
# from (see print_svg.py), plus its eye color.
UNITS = {
    "paul": dict(hair="paul", hair_color="dark", beard="pointed", book=("paul_brown", "paul_purple"), prop=None, iris="#7a4a22"),
    "simon_peter": dict(hair="peter", hair_color="grey", beard="full", book=("blue", "gold"), prop="keys", iris="#4f7ea8"),
    "barnabas": dict(hair="long_beard", hair_color="grey", beard=None, book=("green", "white"), prop="saltire", iris="#5c7c99"),
    "mark": dict(hair="standard_low", hair_color="dark", beard=None, book=("brown", "green"), prop="staff", hat=True, iris="#4f8a4a"),
    "john": dict(hair="flowing", hair_color="dark", beard=None, book=("teal", "crimson"), prop="chalice", iris="#b07a2a", bangs="parted"),
    "philip": dict(hair="standard", hair_color="dark", beard=None, book=("orange", "blue"), prop="cross_staff", iris="#3d6fa8"),
    "timothy": dict(hair="standard", hair_color="dark", beard=None, book=("purple", "white"), prop="knife", iris="#6d4fb0", bangs="spiky"),
    "luke": dict(hair="standard", hair_color="dark", beard=None, book=("green", "gold"), prop="purse", iris="#3f8f7a"),
    "titus": dict(hair="standard", hair_color="dark", beard=None, book=("teal", "orange"), prop="square", iris="#a0602a"),
    "silas": dict(hair="standard", hair_color="dark", beard=None, book=("white", "purple"), prop="club", iris="#5a6fb0"),
    "priscilla": dict(hair="priscilla", hair_color="grey", beard=None, book=("purple", "green"), prop="saw", iris="#8a4fa0", feminine=True),
    "aquila": dict(hair="standard", hair_color="dark", beard=None, book=("orange", "teal"), prop="halberd", iris="#b0612a"),
    "demas": dict(hair="standard", hair_color="dark", beard=None, book=("brown", "slate"), prop="pouch", iris="#6b6b6b"),
}


# --- small SVG helpers -------------------------------------------------------

def pts(points):
    return " ".join(f"{x:.3f},{y:.3f}" for x, y in points)


def poly(points, fill, stroke=INK, width=INK_W, opacity=None):
    extra = f' fill-opacity="{opacity}"' if opacity is not None else ""
    stroke_attr = f'stroke="{stroke}" stroke-width="{width}" stroke-linejoin="round"' if stroke else 'stroke="none"'
    return f'<polygon points="{pts(points)}" fill="{fill}" {stroke_attr}{extra}/>'


def path(d, fill="none", stroke=INK, width=INK_W, opacity=None, cap="round"):
    extra = f' opacity="{opacity}"' if opacity is not None else ""
    stroke_attr = (f'stroke="{stroke}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="{cap}"'
                   if stroke else 'stroke="none"')
    return f'<path d="{d}" fill="{fill}" {stroke_attr}{extra}/>'


def line(a, b, color, width, cap="round", opacity=None):
    extra = f' opacity="{opacity}"' if opacity is not None else ""
    return (f'<line x1="{a[0]:.3f}" y1="{a[1]:.3f}" x2="{b[0]:.3f}" y2="{b[1]:.3f}" '
            f'stroke="{color}" stroke-width="{width}" stroke-linecap="{cap}"{extra}/>')


def inked_line(a, b, color, width, cap="round"):
    """A stroke with an ink outline: a wider dark line under the colored one."""
    return line(a, b, INK, width + INK_W * 2, cap) + line(a, b, color, width, cap)


def ellipse(cx, cy, rx, ry, fill, stroke=None, width=INK_W, opacity=None):
    extra = f' fill-opacity="{opacity}"' if opacity is not None else ""
    stroke_attr = f'stroke="{stroke}" stroke-width="{width}"' if stroke else 'stroke="none"'
    return f'<ellipse cx="{cx:.3f}" cy="{cy:.3f}" rx="{rx:.3f}" ry="{ry:.3f}" fill="{fill}" {stroke_attr}{extra}/>'


def along(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


# --- the stand ----------------------------------------------------------------

def stand():
    """The original isometric stand, unchanged, plus a soft contact shadow
    under the figure so it reads as standing on it rather than floating."""
    return "".join([
        poly([(32, 63), (49, 54.5), (32, 46), (15, 54.5)], "#000000", stroke=None, opacity=0.25),
        poly([(17, 55), (32, 62.5), (32, 60.5), (17, 53)], "#334155", stroke=None),
        poly([(32, 62.5), (47, 55), (47, 53), (32, 60.5)], "#162032", stroke=None),
        poly([(17, 53), (32, 60.5), (47, 53), (32, 45.5)], "#64748b", stroke=None),
        poly([(18, 52.5), (32, 59.5), (46, 52.5), (32, 45.5)], "#3d4b5f", stroke=None),
        poly([(21, 52), (32, 57.5), (43, 52), (32, 46.5)], "#1e293b", stroke=None),
        ellipse(32, 50.2, 5.2, 2.2, "#000000", opacity=0.35),
    ])


# --- head ---------------------------------------------------------------------

# The head's corners: top, right, center, left of the top face, then the
# bottom corners of the two front faces.
T, R, C, L = (32, 30), (38, 33), (32, 36), (26, 33)
LB, B, RB = (26, 38), (32, 41), (38, 38)


def front_edge_y(x):
    """y of the head's top-front edge (L-C-R) at x."""
    return 33 + (x - 26) * 0.5 if x <= 32 else 33 + (38 - x) * 0.5


def head_faces():
    return "".join([
        poly([L, C, B, LB], SKIN["base"], stroke=None),
        poly([C, R, RB, B], SKIN["shade"], stroke=None),
        poly([T, R, C, L], SKIN["light"], stroke=None),
        # Soft cheek light on the lit face.
        ellipse(28.4, 37.2, 1.4, 1.6, SKIN["light"], opacity=0.55),
        # Faint cube edges - kept from the original but drawn as skin-tone
        # shading lines, not ink, so the face still reads as a face.
        line(C, B, SKIN["edge"], 0.14, opacity=0.8),
        path(f"M {L[0]} {L[1]} L {C[0]} {C[1]} L {R[0]} {R[1]}", stroke=SKIN["edge"], width=0.14, opacity=0.8),
    ])


def head_outline():
    return path(f"M {T[0]} {T[1]} L {R[0]} {R[1]} L {RB[0]} {RB[1]} L {B[0]} {B[1]} "
                f"L {LB[0]} {LB[1]} L {L[0]} {L[1]} Z")


def eye(x, y, iris, feminine=False, mirrored=False):
    s = -1 if mirrored else 1
    iris_light = mix(iris, "#ffffff", 0.45)
    parts = [
        ellipse(x, y, 0.82, 0.95, "#ffffff"),
        ellipse(x + 0.04 * s, y + 0.08, 0.62, 0.86, iris),
        ellipse(x + 0.04 * s, y + 0.45, 0.42, 0.32, iris_light, opacity=0.9),
        ellipse(x + 0.04 * s, y + 0.02, 0.3, 0.46, "#150b06"),
        # Upper lash line: thick, sweeping out past the eye's outer corner.
        path(f"M {x - 0.9 * s:.3f} {y - 0.35:.3f} Q {x:.3f} {y - 1.25:.3f} {x + 0.95 * s:.3f} {y - 0.5:.3f}",
             width=0.36),
        path(f"M {x + 0.8 * s:.3f} {y - 0.6:.3f} L {x + 1.15 * s:.3f} {y - 0.35:.3f}", width=0.22),
        path(f"M {x - 0.45 * s:.3f} {y + 0.92:.3f} Q {x:.3f} {y + 1.05:.3f} {x + 0.5 * s:.3f} {y + 0.86:.3f}",
             width=0.1),
        ellipse(x - 0.25 * s, y - 0.32, 0.26, 0.22, "#ffffff"),
        ellipse(x + 0.28 * s, y + 0.38, 0.11, 0.1, "#ffffff"),
    ]
    if feminine:
        parts.append(path(f"M {x + 0.95 * s:.3f} {y - 0.5:.3f} L {x + 1.35 * s:.3f} {y - 0.85:.3f}", width=0.14))
        parts.append(path(f"M {x + 0.7 * s:.3f} {y - 0.75:.3f} L {x + 1.0 * s:.3f} {y - 1.12:.3f}", width=0.12))
    return "".join(parts)


def face(spec):
    parts = [
        eye(30.35, 38.05, spec["iris"], spec.get("feminine"), mirrored=True),
        eye(33.65, 38.05, spec["iris"], spec.get("feminine")),
        ellipse(29.2, 39.35, 0.62, 0.26, BLUSH, opacity=0.5),
        ellipse(34.8, 39.35, 0.62, 0.26, BLUSH, opacity=0.5),
        # Tiny nose.
        path("M 32.12 39.05 L 31.96 39.3", stroke=SKIN["edge"], width=0.16),
    ]
    if spec.get("beard"):
        hair = HAIR[spec["hair_color"]]
        # A mustache in place of a mouth.
        parts.append(path("M 30.9 40.05 Q 31.5 39.55 32 39.85 Q 32.5 39.55 33.1 40.05 Q 32.5 40.35 32 40.1 Q 31.5 40.35 30.9 40.05 Z",
                          fill=hair["base"], width=0.14))
    else:
        mouth = "#c0504a" if spec.get("feminine") else INK
        parts.append(path("M 31.55 39.95 Q 32 40.28 32.45 39.95", stroke=mouth, width=0.16))
    return "".join(parts)


# --- hair ---------------------------------------------------------------------

# The original silhouette of each hair style, drawn behind the head.
BACK_HAIR = {
    "standard": "M 26 32 L 32 28 L 38 32 L 38 36 L 26 36 Z",
    "standard_low": "M 26 33 L 32 29 L 38 33 L 38 37 L 26 37 Z",
    "peter": "M 26 31 L 32 28 L 38 31 L 38 34 L 26 34 Z",
    "priscilla": "M 26 31 L 32 27 L 38 31 L 38 35 L 26 35 Z",
    "long_beard": "M 25 32 L 32 27 L 39 32 L 38 42 L 26 42 Z",
    "flowing": "M 25 32 C 25 25, 39 25, 39 32 L 39 40 L 25 40 Z",
    "paul": "M 28 32 L 32 30.5 L 36 32 L 36 33.5 L 28 33.5 Z",
}

BEARDS = {
    "full": "M 26 38 L 32 43 L 38 38 L 38 41 L 32 44 L 26 41 Z",
    "pointed": "M 27 38 L 32 44 L 37 38 L 36 41 L 32 45 L 28 41 Z",
}


def back_hair(spec):
    hair = HAIR[spec["hair_color"]]
    style = spec["hair"]
    parts = [path(BACK_HAIR[style], fill=hair["base"])]
    if style in ("long_beard", "flowing"):
        # Locks hanging past the head's sides, with strand lines.
        for x0, x1 in ((25.4, 25.7), (26.0, 26.2), (38.0, 37.8), (38.6, 38.3)):
            bottom = 41.5 if style == "long_beard" else 39.5
            parts.append(path(f"M {x0} 34 Q {x0 - 0.3} {bottom - 3} {x1} {bottom}", stroke=hair["shade"], width=0.16))
        parts.append(path(f"M 25.3 33 Q 25.1 36 25.5 38.5", stroke=hair["light"], width=0.2, opacity=0.8))
    if style == "long_beard":
        # The lower part of this silhouette is a long beard below the chin.
        for x in (28.5, 30.3, 32, 33.7, 35.5):
            parts.append(path(f"M {x} 41 Q {x + 0.2} 41.6 {x - 0.1} 42", stroke=hair["shade"], width=0.14))
    return "".join(parts)


def beard(spec):
    if not spec.get("beard"):
        return ""
    hair = HAIR[spec["hair_color"]]
    parts = [path(BEARDS[spec["beard"]], fill=hair["base"])]
    tip = 44.5 if spec["beard"] == "pointed" else 43.5
    for x in (29.2, 30.6, 32, 33.4, 34.8):
        depth = tip - abs(x - 32) * 0.9
        parts.append(path(f"M {x} {41.2 - abs(x - 32) * 0.35:.2f} Q {x + 0.25} {depth - 0.8:.2f} {x - 0.05} {depth - 0.2:.2f}",
                          stroke=hair["shade"], width=0.14))
    parts.append(path("M 27.6 39.6 Q 29.5 41.6 31.2 42.3", stroke=hair["light"], width=0.18, opacity=0.7))
    return "".join(parts)


def bangs_outline(style):
    """The lower edge of the fringe as it falls over the head's front edge,
    from the right corner back to the left one."""
    if style == "parted":
        # Center-parted curtains that sweep out to the sides.
        return [(38, 34.8), (37.2, 35.2), (36.3, 34.9), (35.2, 35.9), (34.2, 35.5),
                (33.2, 36.6), (32.4, 36.1), (32, 35.6), (31.6, 36.1), (30.8, 36.6),
                (29.8, 35.5), (28.8, 35.9), (27.7, 34.9), (26.8, 35.2), (26, 34.8)]
    points = []
    tips = 7 if style == "spiky" else 6
    depth = 0.95 if style == "spiky" else 0.75
    for i in range(tips * 2 + 1):
        x = 38 - 12 * i / (tips * 2)
        base = front_edge_y(x)
        if i in (0, tips * 2):
            points.append((x, base + 1.6))
        elif i % 2:
            wobble = 0.2 * math.sin(i * 1.7)
            points.append((x, base + depth + wobble))
        else:
            points.append((x, base + 0.12))
    return points


def scalp_hair(spec):
    """Hair covering the top of the head, with bangs falling over the
    forehead, strands and a glossy highlight."""
    hair = HAIR[spec["hair_color"]]
    style = spec["hair"]
    if style == "paul":
        # Balding: a bare crown, with hair left only around the sides.
        return "".join([
            poly([(26, 33), (27.6, 32.2), (27.3, 34.7), (26, 35.2)], hair["base"]),
            poly([(38, 33), (36.4, 32.2), (36.7, 34.7), (38, 35.2)], hair["base"]),
            path("M 26.5 33.4 L 26.6 34.6", stroke=hair["shade"], width=0.14),
            path("M 37.5 33.4 L 37.4 34.6", stroke=hair["shade"], width=0.14),
            # A shine on the bald crown.
            ellipse(30.6, 31.6, 1.2, 0.45, "#ffffff", opacity=0.55),
        ])

    bangs_style = spec.get("bangs", "parted" if style == "flowing" else "soft")
    fringe = bangs_outline(bangs_style)
    shape = [T, (38.15, 32.9)] + fringe + [(25.85, 32.9)]
    parts = [poly(shape, hair["base"])]
    # Shade under the fringe's back and along the top.
    parts.append(poly([T, (38, 33), (35.5, 33.2), (32, 31.9), (28.5, 33.2), (26, 33)], hair["shade"], stroke=None, opacity=0.5))
    # Strands running from the crown out to each fringe tip.
    for index, (x, y) in enumerate(fringe[1:-1]):
        if index % 2 == 0:
            parts.append(path(f"M {32 + (x - 32) * 0.25:.2f} {31 + (y - 31) * 0.2:.2f} Q {x + (32 - x) * 0.15:.2f} {y - 1.4:.2f} {x:.2f} {y - 0.15:.2f}",
                              stroke=hair["shade"], width=0.13))
    # The shine: a broken band across the crown.
    for a, b in (((27.8, 33.1), (29.3, 33.55)), ((30.2, 33.8), (31.4, 34.05)), ((32.8, 34.0), (33.9, 33.75)), ((34.8, 33.5), (36.0, 33.1))):
        parts.append(line(a, b, hair["light"], 0.34, opacity=0.9))
    return "".join(parts)


def feminine_locks(spec):
    """Long side locks framing the face - Priscilla's grey hair, grown out."""
    if not spec.get("feminine"):
        return ""
    hair = HAIR[spec["hair_color"]]
    return "".join([
        path("M 26.1 33.2 Q 25.2 36.5 26.2 40.4 Q 26.9 38.5 26.9 35.6 Z", fill=hair["base"], width=0.22),
        path("M 37.9 33.2 Q 38.8 36.5 37.8 40.4 Q 37.1 38.5 37.1 35.6 Z", fill=hair["base"], width=0.22),
        path("M 26.4 35 Q 26.1 37.3 26.4 39.3", stroke=hair["light"], width=0.16),
        path("M 37.6 35 Q 37.9 37.3 37.6 39.3", stroke=hair["shade"], width=0.16),
    ])


def hat():
    """Mark's broad pilgrim-hat brim, behind the head."""
    return "".join([
        path("M 24 31 Q 32 25 40 31", stroke=INK, width=2 + INK_W * 2),
        path("M 24 31 Q 32 25 40 31", stroke="#5a2a0a", width=2),
        path("M 24.8 30.3 Q 32 25 39.2 30.3", stroke="#8a4a1c", width=0.5, opacity=0.9),
    ])


# --- book & hands -------------------------------------------------------------

def book(spec):
    left_name, right_name = spec["book"]
    left_base, left_shade = CLOTH[left_name]
    right_base, right_shade = CLOTH[right_name]
    left = [(28, 41.5), (32, 43.5), (32, 48), (28, 46)]
    right = [(32, 43.5), (36, 41.5), (36, 46), (32, 48)]
    parts = [
        # Page edges showing above the covers.
        poly([(28, 41.5), (32, 43.5), (36, 41.5), (36, 40.9), (32, 42.8), (28, 40.9)], "#f6efdd"),
        path("M 28.4 41.3 L 32 43.1 L 35.6 41.3", stroke="#c9bb99", width=0.1),
        poly(left, left_base),
        poly(right, mix(right_base, right_shade, 0.3)),
        # Tooled border on each cover.
        poly([(28.6, 42.3), (31.4, 43.7), (31.4, 47.1), (28.6, 45.7)], "none", stroke=mix(left_base, "#ffffff", 0.5), width=0.14),
        poly([(32.6, 43.7), (35.4, 42.3), (35.4, 45.7), (32.6, 47.1)], "none", stroke=mix(right_base, "#ffffff", 0.35), width=0.14),
        # A small gold cross on the front cover.
        line((30, 43.6), (30, 45.6), GOLD["base"], 0.3, cap="butt"),
        line((29.3, 44.2), (30.7, 44.9), GOLD["base"], 0.3, cap="butt"),
        # Shadow along the spine.
        poly([(32, 43.5), (32.9, 43.05), (32.9, 47.55), (32, 48)], right_shade, stroke=None, opacity=0.5),
        line((32, 43.5), (32, 48), INK, 0.2),
    ]
    return "".join(parts)


def hands():
    parts = []
    for cx in (28.05, 35.95):
        parts.append(ellipse(cx, 44.2, 0.78, 0.7, SKIN["base"], stroke=INK, width=0.22))
        parts.append(path(f"M {cx - 0.35:.2f} 44.0 L {cx + 0.3:.2f} 44.0", stroke=SKIN["edge"], width=0.1))
    return "".join(parts)


# --- props ---------------------------------------------------------------------

def prop_keys():
    a, b = (39, 45), (44, 30)
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    px, py = uy * -1, -ux * -1  # perpendicular, pointing right
    parts = [inked_line(a, (b[0] - ux * 1.5, b[1] - uy * 1.5), GOLD["base"], 1.0)]
    # The bit: two teeth near the bottom.
    for t in (0.06, 0.16):
        base = along(a, b, t)
        tooth = [base, along(a, b, t + 0.06), (along(a, b, t + 0.06)[0] + px * 1.5, along(a, b, t + 0.06)[1] + py * 1.5),
                 (base[0] + px * 1.5, base[1] + py * 1.5)]
        parts.append(poly(tooth, GOLD["base"], width=0.22))
    parts.append(ellipse(44, 30, 1.5, 1.5, "none", stroke=INK, width=0.8 + INK_W * 2))
    parts.append(ellipse(44, 30, 1.5, 1.5, "none", stroke=GOLD["base"], width=0.8))
    parts.append(path("M 42.9 29.2 Q 43.6 28.5 44.6 28.7", stroke=GOLD["light"], width=0.3))
    parts.append(line(along(a, b, 0.25), along(a, b, 0.8), GOLD["light"], 0.25, opacity=0.9))
    return "".join(parts)


def wood_beam(a, b, width):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    offset = width * 0.22
    return "".join([
        inked_line(a, b, WOOD["base"], width),
        line((a[0] + nx * offset, a[1] + ny * offset), (b[0] + nx * offset, b[1] + ny * offset), WOOD["light"], width * 0.25, opacity=0.8),
    ])


def prop_saltire():
    parts = [wood_beam((18, 48), (28, 32), 1.5), wood_beam((18, 32), (28, 48), 1.5)]
    # Rope lashing where the beams cross.
    parts.append(ellipse(23, 40, 0.95, 0.95, "#d8c08a", stroke=INK, width=0.2))
    parts.append(line((22.3, 39.5), (23.7, 40.5), "#a08850", 0.14))
    parts.append(line((22.3, 40.5), (23.7, 39.5), "#a08850", 0.14))
    return "".join(parts)


def prop_staff(top=25.8):
    parts = [wood_beam((39, 48), (39, top), 1.2)]
    for y in (33.5, 41.0):
        parts.append(line((38.55, y), (39.45, y + 0.35), WOOD["shade"], 0.18))
    # A pilgrim's gourd tied near the top.
    parts.append(line((39.3, 28.4), (40.3, 29.6), "#d8c08a", 0.16))
    parts.append(ellipse(40.6, 30.6, 0.7, 0.8, "#c98a3a", stroke=INK, width=0.2))
    parts.append(ellipse(40.5, 29.55, 0.42, 0.42, "#c98a3a", stroke=INK, width=0.18))
    parts.append(ellipse(40.35, 30.35, 0.22, 0.3, "#f0c27a"))
    return "".join(parts)


def prop_chalice():
    parts = [
        poly([(38, 40), (42, 40), (41, 43), (39, 43)], GOLD["base"]),
        poly([(40, 40), (42, 40), (41, 43), (40, 43)], GOLD["shade"], stroke=None, opacity=0.6),
        ellipse(40, 40, 2, 0.5, "#7a1020", stroke=INK, width=0.2),
        ellipse(40, 40, 2, 0.5, "none", stroke=GOLD["light"], width=0.16),
        inked_line((40, 43), (40, 44.1), GOLD["base"], 0.55, cap="butt"),
        ellipse(40, 44.35, 1.1, 0.38, GOLD["base"], stroke=INK, width=0.2),
        line((38.7, 40.7), (39.3, 42.4), GOLD["light"], 0.3),
        ellipse(40, 41.6, 0.28, 0.28, "#e0314a", stroke=INK, width=0.1),
    ]
    return "".join(parts)


def prop_cross_staff():
    return "".join([
        wood_beam((40, 48), (40, 26), 1.2),
        wood_beam((38, 29), (42, 29), 1.1),
        ellipse(40, 29, 0.42, 0.42, GOLD["base"], stroke=INK, width=0.16),
        line((39.55, 37), (40.45, 37.35), WOOD["shade"], 0.18),
    ])


def prop_knife():
    return "".join([
        poly([(39, 40), (41, 36), (40, 43)], STEEL["base"]),
        poly([(40.1, 38.1), (41, 36), (40, 43)], STEEL["shade"], stroke=None, opacity=0.7),
        line((39.35, 39.9), (40.75, 36.6), STEEL["light"], 0.18),
        inked_line((39.9, 43.1), (39.55, 45), WOOD["base"], 0.7),
        line((38.9, 43.0), (40.9, 43.3), GOLD["base"], 0.35),
    ])


def prop_purse():
    return "".join([
        ellipse(39, 42, 2, 2, "#8a5a1a", stroke=INK, width=INK_W),
        path("M 39.9 40.4 Q 41.3 41.8 40.6 43.6 Q 40 44 39.2 44", fill="#5c3a0e", stroke=None),
        ellipse(38.2, 41.3, 0.7, 0.55, "#b98a42", opacity=0.8),
        path("M 37.9 40.4 Q 39 40.9 40.1 40.4", stroke="#d8c08a", width=0.28),
        ellipse(39, 40, 1, 1, GOLD["base"], stroke=INK, width=0.22),
        ellipse(38.7, 39.7, 0.35, 0.3, GOLD["light"]),
        path("M 37.5 42.8 Q 39 43.4 40.5 42.8", stroke="#5c3a0e", width=0.12),
    ])


def prop_square():
    return "".join([
        path("M 38 42 L 38 34 L 43 34", stroke=INK, width=1.2 + INK_W * 2, cap="butt"),
        path("M 38 42 L 38 34 L 43 34", stroke=GOLD["base"], width=1.2, cap="butt"),
        path("M 37.55 41.8 L 37.55 34.45 L 42.8 34.45", stroke=GOLD["light"], width=0.2),
        "".join(line((38.1, y), (38.55, y), GOLD["shade"], 0.12) for y in (35.5, 36.5, 37.5, 38.5, 39.5, 40.5)),
        "".join(line((x, 33.9), (x, 34.35), GOLD["shade"], 0.12) for x in (39.5, 40.5, 41.5, 42.5)),
    ])


def prop_club():
    return "".join([
        path("M 38.6 46 L 39.5 46.1 L 42.9 30.4 Q 42.3 29.1 41.1 29.8 Z", fill=WOOD["base"]),
        path("M 39.2 45.4 L 41.5 30.6", stroke=WOOD["light"], width=0.3, opacity=0.8),
        ellipse(41.6, 33.5, 0.28, 0.4, WOOD["shade"]),
        ellipse(40.6, 38.0, 0.24, 0.34, WOOD["shade"]),
        line((38.7, 44.2), (39.8, 44.4), "#d8c08a", 0.3),
    ])


def prop_halberd():
    return "".join([
        wood_beam((40, 48), (40, 27.2), 1.2),
        poly([(40, 26.0), (40.55, 27.6), (39.45, 27.6)], STEEL["base"], width=0.2),
        poly([(40, 30), (43, 28), (43.4, 30.5), (43, 33)], STEEL["base"]),
        poly([(40, 30), (43.4, 30.5), (43, 33)], STEEL["shade"], stroke=None, opacity=0.6),
        path("M 42.75 28.6 Q 43.1 30.5 42.75 32.4", stroke=STEEL["light"], width=0.2),
        line((39.5, 30.6), (40.5, 31.0), "#d8c08a", 0.3),
        line((39.5, 31.4), (40.5, 31.8), "#d8c08a", 0.3),
    ])


def prop_saw():
    teeth = "M 39.7 32.2 " + " ".join(f"L 40.9 {y + 0.55:.2f} L 39.7 {y + 1.1:.2f}" for y in np.arange(32.2, 41.2, 1.1))
    return "".join([
        path(teeth, fill=STEEL["shade"], width=0.18),
        poly([(38.3, 32), (39.7, 32), (39.7, 42.5), (38.3, 42.5)], STEEL["base"]),
        line((38.65, 32.4), (38.65, 42.1), STEEL["light"], 0.25),
        poly([(38.2, 42.5), (39.8, 42.5), (39.6, 46.4), (38.4, 46.4)], WOOD["base"]),
        ellipse(39, 44.4, 0.3, 0.55, WOOD["shade"]),
    ])


def prop_pouch():
    return "".join([
        ellipse(23, 42, 2.5, 2, "#94a3b8", stroke=INK, width=INK_W),
        path("M 24.1 40.3 Q 25.8 41.6 25.1 43.4 Q 24.2 44 23 44", fill="#64748b", stroke=None),
        ellipse(22.1, 41.3, 0.9, 0.6, "#dbe3ec", opacity=0.8),
        path("M 21.6 40.3 Q 23 40.9 24.4 40.3", stroke="#475569", width=0.3),
        poly([(23, 40), (22, 38), (24, 38)], GOLD["base"], width=0.22),
        ellipse(22.3, 39.2, 0.45, 0.2, "#e2e8f0", stroke=INK, width=0.12),
        ellipse(23.8, 39.4, 0.45, 0.2, "#e2e8f0", stroke=INK, width=0.12),
    ])


PROPS = {
    "keys": prop_keys, "saltire": prop_saltire, "staff": prop_staff, "chalice": prop_chalice,
    "cross_staff": prop_cross_staff, "knife": prop_knife, "purse": prop_purse, "square": prop_square,
    "club": prop_club, "halberd": prop_halberd, "saw": prop_saw, "pouch": prop_pouch,
}
# Props drawn behind the figure rather than in front of it (Barnabas's
# cross is on his back).
BEHIND = {"saltire"}


# --- assembly -------------------------------------------------------------------

def mix(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def figure_svg(spec):
    prop = PROPS[spec["prop"]]() if spec.get("prop") else ""
    body = [stand()]
    if spec.get("prop") in BEHIND:
        body.append(prop)
    if spec.get("hat"):
        body.append(hat())
    body += [
        back_hair(spec),
        beard(spec),
        head_faces(),
        face(spec),
        head_outline(),
        scalp_hair(spec),
        feminine_locks(spec),
        book(spec),
        hands(),
    ]
    if spec.get("prop") and spec["prop"] not in BEHIND:
        body.append(prop)

    view_x, view_y = -ORIGIN_X / FIGURE_SCALE, -ORIGIN_Y / FIGURE_SCALE
    view_w, view_h = CANVAS_W / FIGURE_SCALE, CANVAS_H / FIGURE_SCALE
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_x:.4f} {view_y:.4f} {view_w:.4f} {view_h:.4f}" '
            f'width="{CANVAS_W}" height="{CANVAS_H}">' + "".join(body) + "</svg>")


def render_png(svg, out_path):
    page = pymupdf.open(stream=svg.encode("utf-8"), filetype="svg")[0]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(SUPERSAMPLE, SUPERSAMPLE), alpha=True)
    rgba = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 4).astype(np.float32)
    # PyMuPDF hands back premultiplied alpha; PNG wants it straight.
    alpha = rgba[:, :, 3:4]
    rgba[:, :, :3] = np.where(alpha > 0, np.clip(rgba[:, :, :3] * 255 / np.maximum(alpha, 1), 0, 255), 0)
    Image.fromarray(rgba.astype(np.uint8), "RGBA").save(out_path)


def main():
    svg_dir = os.path.join(HERE, "unit_svg")
    os.makedirs(svg_dir, exist_ok=True)
    for name, spec in UNITS.items():
        svg = figure_svg(spec)
        with open(os.path.join(svg_dir, f"{name}.svg"), "w", encoding="utf-8") as f:
            f.write(svg)
        render_png(svg, os.path.join(HERE, f"{name}.png"))
        print(f"rendered {name}.png")


if __name__ == "__main__":
    main()

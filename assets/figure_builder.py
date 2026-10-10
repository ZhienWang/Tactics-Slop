"""Builds full-body chibi unit tokens from parts, for the character generator
(tools/character_generator.py).

The original units (assets/unit_art.py) are standees - a cube head holding a
book. These figures add a body, arms and legs, plus helmets, capes and
weapons, in the same style: flat cel colours, ink outlines, and the same
isometric stand and 2:1 canvas, so they sit on the map like every other unit.

A design is a plain dict (see DEFAULT_SPEC and OPTIONS); figure_svg(spec)
turns it into SVG and render_png / render_rgba rasterise it.
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import unit_art as ua  # noqa: E402
from unit_art import INK, INK_W, CLOTH, GOLD, STEEL, WOOD, ellipse, inked_line, line, mix, path, poly  # noqa: E402

# --- palettes ---------------------------------------------------------------------

SKINS = {
    "light": {"base": "#fcd5ae", "shade": "#efb68c", "light": "#ffe4c8", "edge": "#e6a57c"},
    "olive": {"base": "#e2b484", "shade": "#c8935f", "light": "#f0cda3", "edge": "#b8814f"},
    "tan": {"base": "#c98f5c", "shade": "#a9713f", "light": "#dcaa7a", "edge": "#93602f"},
    "brown": {"base": "#9a6339", "shade": "#7a4a26", "light": "#b47b4e", "edge": "#643a1b"},
    "dark": {"base": "#6b4126", "shade": "#4f2d18", "light": "#83553a", "edge": "#3e2212"},
}
HAIR_COLORS = {
    "dark": {"base": "#4a2a14", "shade": "#2c170a", "light": "#9a6a44"},
    "black": {"base": "#26201c", "shade": "#120e0b", "light": "#5c5450"},
    "auburn": {"base": "#8a3a1a", "shade": "#5a210c", "light": "#c56a3e"},
    "blond": {"base": "#d9a94a", "shade": "#a6772a", "light": "#f3d98f"},
    "grey": {"base": "#a7b1bf", "shade": "#6f7a8a", "light": "#eef2f7"},
    "white": {"base": "#e9e6df", "shade": "#b9b3a8", "light": "#ffffff"},
}
IRISES = {"brown": "#7a4a22", "blue": "#4f7ea8", "green": "#4f8a4a", "grey": "#6b6b6b", "amber": "#b07a2a", "violet": "#6d4fb0"}
BRONZE = {"base": "#c98a3a", "shade": "#8a5a1a", "light": "#f0c27a"}

# Every choice the generator offers, in the order it cycles through them.
OPTIONS = {
    "head": ["round", "oval", "wide", "heart", "small"],
    "skin": list(SKINS),
    "eyes": ["bright", "narrow", "fierce", "closed"],
    "iris": list(IRISES),
    "mouth": ["smile", "cat", "neutral", "frown", "open"],
    "hair": ["standard", "short", "flowing", "long", "bald", "none"],
    "hair_color": list(HAIR_COLORS),
    "beard": ["none", "full", "pointed", "mustache", "stubble"],
    "body": ["robe", "tunic", "armor", "toga"],
    "main": [c for c in CLOTH if not c.startswith("paul_")],
    "trim": [c for c in CLOTH if not c.startswith("paul_")],
    "arms": ["sides", "book", "raised", "hold"],
    "legs": ["robe", "sandals", "greaves", "trousers"],
    "helmet": ["none", "legionary", "centurion", "hood", "headwrap", "crown", "laurel"],
    "cape": ["none", "short", "long"],
    "cape_color": [c for c in CLOTH if not c.startswith("paul_")],
    "weapon": ["none", "sword", "spear", "shield", "sword_shield", "bow", "staff", "sling", "club",
               "keys", "chalice", "cross_staff", "knife", "purse", "saw", "halberd"],
    "feminine": [False, True],
}
DEFAULT_SPEC = {
    "head": "round", "skin": "light", "eyes": "bright", "iris": "brown", "mouth": "smile",
    "hair": "standard", "hair_color": "dark", "beard": "none", "body": "robe", "main": "blue", "trim": "gold",
    "arms": "book", "legs": "robe", "helmet": "none", "cape": "none", "cape_color": "crimson", "weapon": "none",
    "feminine": False,
}


# --- head -------------------------------------------------------------------------
# A soft, round chibi head - wider than tall, with big glossy eyes - in place
# of the original units' cube. Everything on it (face, hair, beard, helmet)
# is placed from this centre and radius; the other head shapes are this
# head stretched about the chin, so all of it follows along.
HX, HY = 32.0, 35.2          # centre
HRX, HRY = 6.7, 6.0          # radii (chin at HY + HRY = 41.2, on the shoulders)
CHIN = (HX, HY + HRY)
HEAD_TRANSFORMS = {
    "round": "",
    "heart": "",
    "oval": f"translate({CHIN[0]} {CHIN[1]}) scale(0.92 1.1) translate({-CHIN[0]} {-CHIN[1]})",
    "wide": f"translate({CHIN[0]} {CHIN[1]}) scale(1.13 0.95) translate({-CHIN[0]} {-CHIN[1]})",
    "small": f"translate({CHIN[0]} {CHIN[1]}) scale(0.86 0.86) translate({-CHIN[0]} {-CHIN[1]})",
}


def head_point(angle, shape="round", grow=0.0):
    """A point on the head's outline; angle 0 = right, 90 = chin (degrees).
    A heart head narrows toward a soft point at the chin."""
    a = math.radians(angle)
    x, y = math.cos(a) * (HRX + grow), math.sin(a) * (HRY + grow)
    if shape == "heart" and y > 0:
        x *= 1 - 0.32 * (y / HRY) ** 1.6
        y *= 1 + 0.06 * (y / HRY)
    return HX + x, HY + y


def head_outline_points(shape, grow=0.0, steps=48):
    return [head_point(i * 360 / steps, shape, grow) for i in range(steps)]


def pts_path(points, close=True):
    d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points)
    return d + (" Z" if close else "")


def head(spec, skin):
    shape = spec["head"] if spec["head"] == "heart" else "round"
    outline = head_outline_points(shape)
    # Shadow: a crescent down the right side, between the outline and an
    # ellipse nudged left.
    shade = [head_point(a, shape) for a in range(-80, 101, 6)]
    shade += [(HX - 1.6 + math.cos(math.radians(a)) * (HRX - 0.2), HY + math.sin(math.radians(a)) * (HRY - 0.2))
              for a in range(100, -81, -6)]
    ears = "".join([
        ellipse(HX - HRX + 0.3, HY + 1.0, 1.0, 1.3, skin["base"], stroke=INK, width=INK_W),
        ellipse(HX + HRX - 0.3, HY + 1.0, 1.0, 1.3, skin["shade"], stroke=INK, width=INK_W),
        ellipse(HX - HRX + 0.4, HY + 1.0, 0.45, 0.7, skin["edge"], opacity=0.6),
    ])
    faces = "".join([
        ears,
        path(pts_path(outline), fill=skin["base"], stroke=None),
        path(pts_path(shade), fill=skin["shade"], stroke=None, opacity=0.75),
        # A soft light on the forehead and cheek.
        ellipse(HX - 2.4, HY - 3.0, 2.2, 1.1, skin["light"], opacity=0.75),
        ellipse(HX - 3.4, HY + 2.2, 1.1, 0.9, skin["light"], opacity=0.5),
    ])
    return faces, path(pts_path(outline))


EYE_Y = HY + 1.0
EYE_X = (HX - 2.45, HX + 2.45)


def cute_eye(x, y, iris, feminine, mirrored):
    s = -1 if mirrored else 1
    dark = mix(iris, "#000000", 0.55)
    light = mix(iris, "#ffffff", 0.5)
    parts = [
        ellipse(x, y, 1.05, 1.42, dark, stroke=INK, width=0.22),
        ellipse(x, y + 0.25, 0.86, 1.1, iris),
        ellipse(x, y + 0.75, 0.62, 0.48, light, opacity=0.9),
        ellipse(x, y - 0.05, 0.42, 0.55, "#140a05"),
        # Two sparkles: a big one up and out, a small one low and in.
        ellipse(x - 0.4 * s, y - 0.55, 0.38, 0.42, "#ffffff"),
        ellipse(x + 0.35 * s, y + 0.55, 0.16, 0.16, "#ffffff"),
        # Upper lash line, flicking out at the corner.
        path(f"M {x - 1.15 * s:.2f} {y - 0.75:.2f} Q {x:.2f} {y - 1.75:.2f} {x + 1.15 * s:.2f} {y - 0.85:.2f}", width=0.38),
    ]
    if feminine:
        parts.append(path(f"M {x + 1.1 * s:.2f} {y - 0.85:.2f} L {x + 1.55 * s:.2f} {y - 1.25:.2f}", width=0.18))
        parts.append(path(f"M {x + 0.8 * s:.2f} {y - 1.2:.2f} L {x + 1.1 * s:.2f} {y - 1.65:.2f}", width=0.15))
    return "".join(parts)


def eyes(spec):
    iris = IRISES[spec["iris"]]
    fem = spec.get("feminine")
    style = spec["eyes"]
    if style == "closed":
        # Happy closed eyes: little upward arcs.
        return "".join(path(f"M {x - 1.0:.2f} {EYE_Y + 0.2:.2f} Q {x:.2f} {EYE_Y - 0.9:.2f} {x + 1.0:.2f} {EYE_Y + 0.2:.2f}", width=0.36)
                       for x in EYE_X)
    if style == "narrow":
        parts = []
        for x in EYE_X:
            parts.append(ellipse(x, EYE_Y + 0.2, 0.95, 0.55, mix(iris, "#000000", 0.4), stroke=INK, width=0.2))
            parts.append(ellipse(x - 0.3, EYE_Y + 0.05, 0.22, 0.18, "#ffffff"))
            parts.append(path(f"M {x - 1.1:.2f} {EYE_Y - 0.25:.2f} L {x + 1.1:.2f} {EYE_Y - 0.25:.2f}", width=0.36))
        return "".join(parts)
    parts = [cute_eye(EYE_X[0], EYE_Y, iris, fem, mirrored=True), cute_eye(EYE_X[1], EYE_Y, iris, fem, mirrored=False)]
    if style == "fierce":
        parts.append(path(f"M {EYE_X[0] - 1.2:.2f} {EYE_Y - 2.3:.2f} L {EYE_X[0] + 1.0:.2f} {EYE_Y - 1.5:.2f}", width=0.45))
        parts.append(path(f"M {EYE_X[1] + 1.2:.2f} {EYE_Y - 2.3:.2f} L {EYE_X[1] - 1.0:.2f} {EYE_Y - 1.5:.2f}", width=0.45))
    return "".join(parts)


MOUTH_Y = HY + 3.4


def mouth(spec, hair):
    my = MOUTH_Y
    if spec["beard"] in ("full", "pointed", "mustache"):
        return path(f"M {HX - 1.3:.2f} {my - 0.1:.2f} Q {HX - 0.6:.2f} {my - 0.75:.2f} {HX:.2f} {my - 0.35:.2f} "
                    f"Q {HX + 0.6:.2f} {my - 0.75:.2f} {HX + 1.3:.2f} {my - 0.1:.2f} Q {HX:.2f} {my + 0.3:.2f} {HX - 1.3:.2f} {my - 0.1:.2f} Z",
                    fill=hair["base"], width=0.16)
    color = "#b8483f" if spec.get("feminine") else INK
    shapes = {
        "smile": f"M {HX - 0.55:.2f} {my - 0.1:.2f} Q {HX:.2f} {my + 0.45:.2f} {HX + 0.55:.2f} {my - 0.1:.2f}",
        "neutral": f"M {HX - 0.45:.2f} {my + 0.05:.2f} L {HX + 0.45:.2f} {my + 0.05:.2f}",
        "frown": f"M {HX - 0.55:.2f} {my + 0.25:.2f} Q {HX:.2f} {my - 0.25:.2f} {HX + 0.55:.2f} {my + 0.25:.2f}",
        # A little cat mouth.
        "cat": f"M {HX - 0.7:.2f} {my - 0.05:.2f} Q {HX - 0.35:.2f} {my + 0.4:.2f} {HX:.2f} {my:.2f} Q {HX + 0.35:.2f} {my + 0.4:.2f} {HX + 0.7:.2f} {my - 0.05:.2f}",
    }
    if spec["mouth"] == "open":
        return "".join([path(f"M {HX - 0.6:.2f} {my - 0.15:.2f} Q {HX:.2f} {my + 1.0:.2f} {HX + 0.6:.2f} {my - 0.15:.2f} Z",
                             fill="#8a2a24", width=0.2),
                        ellipse(HX, my + 0.38, 0.28, 0.14, "#e86a6a")])
    return path(shapes[spec["mouth"]], stroke=color, width=0.2)


def face(spec, skin, hair):
    parts = [eyes(spec),
             # Rosy blush under each eye.
             ellipse(EYE_X[0] - 0.9, EYE_Y + 1.85, 0.95, 0.42, ua.BLUSH, opacity=0.55),
             ellipse(EYE_X[1] + 0.9, EYE_Y + 1.85, 0.95, 0.42, ua.BLUSH, opacity=0.55),
             mouth(spec, hair)]
    if spec["beard"] == "stubble":
        parts += [ellipse(HX + dx, MOUTH_Y + 0.9 + abs(dx) * -0.12, 0.09, 0.09, hair["shade"], opacity=0.7)
                  for dx in (-2.2, -1.4, -0.6, 0.6, 1.4, 2.2, 0)]
    return "".join(parts)


def beard(spec, hair):
    kind = spec["beard"]
    if kind not in ("full", "pointed"):
        return ""
    shape = "heart" if spec["head"] == "heart" else "round"
    # Follows the jaw from cheek to cheek, hanging below the chin.
    jaw = [head_point(a, shape, 0.25) for a in range(28, 153, 6)]
    hang = 2.2 if kind == "full" else 3.2
    lower = []
    for x, y in reversed(jaw):
        t = 1 - abs(x - HX) / HRX
        drop = hang * (t ** (0.8 if kind == "full" else 1.6))
        lower.append((x, y + drop))
    parts = [path(pts_path(jaw[::-1] + lower[::-1]), fill=hair["base"])]
    for dx in (-2.6, -1.3, 0, 1.3, 2.6):
        x = HX + dx
        y0 = MOUTH_Y + 1.2
        parts.append(path(f"M {x:.2f} {y0:.2f} Q {x + 0.3:.2f} {y0 + hang * 0.6:.2f} {x - 0.05:.2f} {y0 + hang * 0.9 - abs(dx) * 0.3:.2f}",
                          stroke=hair["shade"], width=0.15))
    return "".join(parts)


def hair_parts(spec, hair):
    """(behind the head, on top of it) for the chosen hair style - a fluffy
    cap following the round head, with scalloped bangs and a little tuft."""
    style = spec["hair"]
    if style == "none":
        return "", ""
    base, shade, light = hair["base"], hair["shade"], hair["light"]
    shape = "heart" if spec["head"] == "heart" else "round"
    back = ""
    if style in ("flowing", "long"):
        bottom = 42.5 if style == "flowing" else 45.5
        back = path(f"M {HX - HRX - 0.9:.2f} {HY:.2f} Q {HX - HRX - 1.3:.2f} {bottom - 2:.2f} {HX - HRX + 0.4:.2f} {bottom:.2f} "
                    f"L {HX + HRX - 0.4:.2f} {bottom:.2f} Q {HX + HRX + 1.3:.2f} {bottom - 2:.2f} {HX + HRX + 0.9:.2f} {HY:.2f} Z",
                    fill=base)
        back += path(f"M {HX + HRX:.2f} {HY + 1:.2f} Q {HX + HRX + 0.8:.2f} {bottom - 2.5:.2f} {HX + HRX - 0.6:.2f} {bottom - 0.3:.2f}",
                     stroke=shade, width=0.2)
    if style == "bald":
        top = "".join([
            path(pts_path([head_point(a, shape, 0.2) for a in range(150, 196, 5)] + [(HX - HRX + 1.6, HY + 0.6)]), fill=base),
            path(pts_path([head_point(a, shape, 0.2) for a in range(-15, 31, 5)] + [(HX + HRX - 1.6, HY + 0.6)]), fill=base),
            ellipse(HX - 1.8, HY - 3.6, 1.6, 0.6, "#ffffff", opacity=0.55),
        ])
        return back, top
    # The cap: the top of the head, a little puffed out, down to the bangs.
    cap = [head_point(a, shape, 0.55) for a in range(178, 363, 6)]
    side_drop = 2.4 if style in ("flowing", "long") else 0.9
    right_side = (HX + HRX + 0.3, HY + side_drop)
    left_side = (HX - HRX - 0.3, HY + side_drop)
    # Scalloped bangs across the forehead, from right to left.
    tips = 5 if style != "short" else 7
    bangs = []
    for i in range(tips * 2 + 1):
        t = i / (tips * 2)
        x = HX + HRX - 0.6 - t * (HRX * 2 - 1.2)
        rise = 0.9 if i % 2 == 0 else -0.55
        y = HY - 2.0 + rise + abs(t - 0.5) * 2.0
        bangs.append((x, y))
    if style == "standard":
        # Swept to one side: deeper on the left.
        bangs = [(x, y + (x - HX) * -0.12) for x, y in bangs]
    outline = cap + [right_side] + bangs + [left_side]
    parts = [path(pts_path(outline), fill=base)]
    # Shade along the right of the cap, and strands into each bang tip.
    parts.append(path(pts_path([head_point(a, shape, 0.5) for a in range(300, 363, 6)] + [(HX + HRX - 1.2, HY - 1.2), (HX + 1.5, HY - 4.8)]),
                      fill=shade, stroke=None, opacity=0.6))
    for i, (x, y) in enumerate(bangs):
        if i % 2 == 0 and 0 < i < len(bangs) - 1:
            parts.append(path(f"M {HX + (x - HX) * 0.4:.2f} {HY - 5.2:.2f} Q {x + (HX - x) * 0.1:.2f} {y - 1.6:.2f} {x:.2f} {y - 0.2:.2f}",
                              stroke=shade, width=0.15))
    # A glossy shine band across the crown.
    parts.append(path(f"M {HX - 4.2:.2f} {HY - 3.6:.2f} Q {HX - 2.6:.2f} {HY - 5.3:.2f} {HX - 0.6:.2f} {HY - 5.5:.2f}", stroke=light, width=0.45))
    if style == "short":
        # Spiky tufts on top.
        for dx in (-2.6, -0.4, 1.9):
            tx, ty = head_point(270 + dx * 9, shape, 0.5)
            parts.append(poly([(tx - 0.9, ty + 0.6), (tx + dx * 0.15, ty - 1.6), (tx + 0.9, ty + 0.6)], base, width=0.22))
    else:
        # The little cowlick tuft.
        tx, ty = head_point(282, shape, 0.5)
        parts.append(path(f"M {tx - 0.3:.2f} {ty + 0.3:.2f} Q {tx + 0.6:.2f} {ty - 2.0:.2f} {tx + 1.9:.2f} {ty - 1.5:.2f} "
                          f"Q {tx + 0.8:.2f} {ty - 1.0:.2f} {tx + 0.5:.2f} {ty + 0.3:.2f} Z", fill=base, width=0.22))
    if style == "long" or spec.get("feminine"):
        # Locks framing the face.
        for sx in (-1, 1):
            x = HX + sx * (HRX - 0.2)
            parts.append(path(f"M {x:.2f} {HY - 1:.2f} Q {x + sx * 1.0:.2f} {HY + 3:.2f} {x - sx * 0.2:.2f} {HY + 5.6:.2f} "
                              f"Q {x - sx * 0.9:.2f} {HY + 3:.2f} {x - sx * 0.9:.2f} {HY - 0.6:.2f} Z", fill=base, width=0.22))
    return back, "".join(parts)


# --- helmets ----------------------------------------------------------------------

def helmet(spec):
    kind = spec["helmet"]
    if kind == "none":
        return ""
    T, R, L = ua.T, ua.R, ua.L
    if kind in ("legionary", "centurion"):
        dome = "M 25.4 34.2 Q 25.2 28.6 32 27.4 Q 38.8 28.6 38.6 34.2 L 38.2 34.6 Q 32 32.2 25.8 34.6 Z"
        parts = [
            path(dome, fill=STEEL["base"]),
            path("M 32 27.6 Q 37.6 28.8 38.3 33.6 Q 35 32.4 32 32.3 Z", fill=STEEL["shade"], stroke=None, opacity=0.6),
            path("M 27.2 31.4 Q 29 29 32 28.5", stroke=STEEL["light"], width=0.35),
            path("M 25.4 34.4 Q 32 31.9 38.6 34.4", stroke=BRONZE["base"], width=0.55),
            # Cheek guards.
            path("M 25.7 34.6 L 25.9 38.6 L 27.3 39.3 L 27.4 35.4 Z", fill=STEEL["base"], width=0.22),
            path("M 38.3 34.6 L 38.1 38.6 L 36.7 39.3 L 36.6 35.4 Z", fill=STEEL["shade"], width=0.22),
            # Neck guard.
            path("M 38.6 33.6 L 40.2 35 L 39.6 35.6 L 38.4 34.6 Z", fill=STEEL["shade"], width=0.2),
        ]
        crest_color = "#c0262c"
        if kind == "legionary":
            parts.append(path("M 29.5 28.4 Q 32 24.2 34.5 28.4 Q 32 27.4 29.5 28.4 Z", fill=crest_color, width=0.24))
            parts.append(path("M 30.4 27.2 Q 32 25.2 33.6 27.2", stroke="#ef6a6a", width=0.18))
        else:
            # A centurion's crest runs side to side.
            parts.append(path("M 24.6 28.6 Q 32 23.0 39.4 28.6 L 38.6 29.4 Q 32 25.4 25.4 29.4 Z", fill=crest_color, width=0.24))
            for x in (27, 29.5, 32, 34.5, 37):
                parts.append(line((x, 26.6 + abs(x - 32) * 0.28), (x, 27.9 + abs(x - 32) * 0.2), "#7a1418", 0.14))
        return "".join(parts)
    if kind == "hood":
        return "".join([
            path("M 24.8 35 Q 24.2 27.4 32 26.8 Q 39.8 27.4 39.2 35 L 39.4 40.4 L 37.6 39.6 Q 38.2 31.6 32 31.4 Q 25.8 31.6 26.4 39.6 L 24.6 40.4 Z",
                 fill=CLOTH[spec["cape_color"]][0]),
            path("M 32 27 Q 38.8 27.6 39.2 35 L 39.3 40 L 37.7 39.4 Q 38.1 31.8 32 31.5 Z", fill=CLOTH[spec["cape_color"]][1],
                 stroke=None, opacity=0.6),
        ])
    if kind == "headwrap":
        base, shade = CLOTH[spec["trim"]]
        return "".join([
            path("M 25.6 33.6 Q 25.6 28.4 32 28 Q 38.4 28.4 38.4 33.6 Q 32 31.6 25.6 33.6 Z", fill=base),
            path("M 25.6 33.6 Q 32 31.6 38.4 33.6 L 38.4 34.8 Q 32 32.8 25.6 34.8 Z", fill=shade, width=0.22),
            path("M 27 30.6 Q 32 29.2 37 30.6", stroke=shade, width=0.18),
            path("M 38.2 34.2 Q 39.6 36.4 38.8 38.6 L 38.1 38.2 Q 38.6 36.4 37.8 34.6 Z", fill=base, width=0.2),
        ])
    if kind == "crown":
        pts = [(26.6, 32.6), (26.6, 29.8), (28.4, 31.2), (30.2, 29), (32, 30.8), (33.8, 29), (35.6, 31.2), (37.4, 29.8), (37.4, 32.6),
               (32, 33.6)]
        return "".join([poly(pts, GOLD["base"], width=0.25), path("M 27 32.2 L 32 33.2 L 37 32.2", stroke=GOLD["shade"], width=0.2),
                        ellipse(32, 31.9, 0.42, 0.42, "#c0262c", stroke=INK, width=0.12),
                        ellipse(28.9, 31.6, 0.3, 0.3, "#2563eb", stroke=INK, width=0.1),
                        ellipse(35.1, 31.6, 0.3, 0.3, "#16a34a", stroke=INK, width=0.1)])
    if kind == "laurel":
        parts = [path("M 26 33.4 Q 32 30.4 38 33.4", stroke="#3f6b2a", width=0.3)]
        for i in range(9):
            t = i / 8
            x = 26.4 + 11.2 * t
            y = 33.2 - math.sin(t * math.pi) * 2.6
            parts.append(ellipse(x, y - 0.4, 0.5, 0.28, "#6aa84f", stroke=INK, width=0.1))
        return "".join(parts)
    return ""


# --- body -------------------------------------------------------------------------

# The torso: a front-facing chest, lit on the left and shaded on the right
# like the head, from the shoulders (y~41) to the hips (y~48).
TORSO_L = [(27.3, 41.3), (32, 41.7), (32, 48.4), (28.1, 47.9)]
TORSO_R = [(32, 41.7), (36.7, 41.3), (35.9, 47.9), (32, 48.4)]


def cape(spec, behind=True):
    if spec["cape"] == "none":
        return ""
    base, shade = CLOTH[spec["cape_color"]]
    bottom = 52.2 if spec["cape"] == "long" else 47.4
    return "".join([
        path(f"M 26.6 40.6 Q 23.6 46 24.2 {bottom} Q 32 {bottom + 2.4:.1f} 39.8 {bottom} Q 40.4 46 37.4 40.6 Z", fill=shade),
        path(f"M 37.4 40.6 Q 39.8 45 39.4 {bottom - 0.6:.1f}", stroke=mix(base, "#ffffff", 0.3), width=0.25),
    ])


def torso(spec):
    kind = spec["body"]
    main, main_shade = CLOTH[spec["main"]]
    trim, trim_shade = CLOTH[spec["trim"]]
    if kind == "armor":
        parts = [
            # Tunic skirt under the armour, with leather strips (pteruges).
            path("M 28.2 47.4 Q 32 48.6 35.8 47.4 L 36.2 50.2 Q 32 51.6 27.8 50.2 Z", fill=main),
            "".join(line((x, 48.2), (x + (x - 32) * 0.08, 50.6 - abs(x - 32) * 0.12), BRONZE["shade"], 0.6) for x in (29, 30.5, 32, 33.5, 35)),
            poly(TORSO_L, STEEL["base"]),
            poly(TORSO_R, STEEL["shade"]),
        ]
        # Segmented plates across the chest, and a light catching the left side.
        for y in (43.4, 45.0, 46.6):
            parts.append(path(f"M 27.7 {y:.1f} Q 32 {y + 0.7:.1f} 36.3 {y:.1f}", stroke=mix(STEEL["shade"], INK, 0.4), width=0.24))
        parts.append(path("M 28.4 42.1 L 28.8 47.2", stroke=STEEL["light"], width=0.32))
        parts.append(path("M 28 47.9 Q 32 48.9 36 47.9", stroke=BRONZE["base"], width=0.55))
        # Shoulder plates.
        parts.append(path("M 26.2 42.6 Q 26.6 40.6 28.6 40.9 L 28.8 42.6 Q 27.4 42.2 26.2 42.6 Z", fill=STEEL["base"], width=0.22))
        parts.append(path("M 37.8 42.6 Q 37.4 40.6 35.4 40.9 L 35.2 42.6 Q 36.6 42.2 37.8 42.6 Z", fill=STEEL["shade"], width=0.22))
        return "".join(parts)
    long_hem = kind in ("robe", "toga") or spec["legs"] == "robe"
    bottom = 52.4 if long_hem else 48.4
    left = [TORSO_L[0], TORSO_L[1], (32, bottom), (27.6 if long_hem else 28.1, bottom - 0.6)]
    right = [TORSO_R[0], TORSO_R[1], (36.4 if long_hem else 35.9, bottom - 0.6), (32, bottom)]
    parts = [poly(left, main), poly(right, mix(main, main_shade, 0.45))]
    # Hem trim, a neckline, and a centre seam.
    parts.append(path(f"M 27.8 {bottom - 0.9:.1f} Q 32 {bottom + 0.1:.1f} 36.2 {bottom - 0.9:.1f}", stroke=trim, width=0.45))
    parts.append(path("M 30.4 41.6 Q 32 43 33.6 41.6", stroke=trim, width=0.4))
    if kind in ("robe", "tunic"):
        parts.append(path("M 27.9 45.4 Q 32 46.4 36.1 45.4", stroke=trim_shade, width=0.75))  # belt
        parts.append(ellipse(32, 45.95, 0.45, 0.4, GOLD["base"], stroke=INK, width=0.12))
        parts.append(path(f"M 32 46.4 L 32 {bottom - 0.4:.1f}", stroke=main_shade, width=0.18))
    if kind == "toga":
        parts.append(path("M 27.5 41.5 Q 31 44.4 36.1 46.6 L 35.9 48.2 Q 30.6 45.8 27.6 43.4 Z", fill=trim, width=0.22))
    return "".join(parts)


def legs(spec, skin):
    kind = spec["legs"]
    if kind == "robe" or spec["body"] in ("robe", "toga"):
        # Only the feet peek out under a long hem.
        return "".join(ellipse(x, 52.6, 0.95, 0.5, "#5a3a1e", stroke=INK, width=0.18) for x in (30.4, 33.6))
    parts = []
    for x in (30.4, 33.6):
        if kind == "greaves":
            parts.append(inked_line((x, 48), (x, 52.2), skin["base"], 1.3, cap="butt"))
            parts.append(poly([(x - 0.75, 48.8), (x + 0.75, 48.8), (x + 0.7, 51.8), (x - 0.7, 51.8)], STEEL["base"], width=0.2))
            parts.append(line((x - 0.4, 49.1), (x - 0.4, 51.5), STEEL["light"], 0.18))
        elif kind == "trousers":
            trim, trim_shade = CLOTH[spec["trim"]]
            parts.append(inked_line((x, 48), (x, 52.1), trim if x < 32 else trim_shade, 1.4, cap="butt"))
        else:  # sandals
            parts.append(inked_line((x, 48), (x, 52.2), skin["base"] if x < 32 else skin["shade"], 1.2, cap="butt"))
            for y in (50.4, 51.4):
                parts.append(line((x - 0.65, y), (x + 0.65, y + 0.3), "#7a4a22", 0.22))
        parts.append(ellipse(x + 0.15, 52.6, 1.0, 0.5, "#5a3a1e", stroke=INK, width=0.18))
    return "".join(parts)


def arms(spec, skin):
    """(behind the torso, in front) - sleeves in the body's colour, ending in
    hands. Returns where the right hand is, for weapons."""
    kind = spec["arms"]
    main, main_shade = CLOTH[spec["main"]] if spec["body"] != "armor" else (skin["base"], skin["shade"])
    sleeve_l, sleeve_r = main, mix(main, main_shade, 0.45)
    shoulder_l, shoulder_r = (27.6, 41.8), (36.4, 41.8)
    if kind == "book":
        hand_l, hand_r = (28.05, 44.2), (35.95, 44.2)
    elif kind == "raised":
        hand_l, hand_r = (26.6, 46.2), (39.4, 36.6)
    elif kind == "hold":
        hand_l, hand_r = (26.8, 46.0), (38.6, 45.0)
    else:  # sides
        hand_l, hand_r = (26.7, 46.4), (37.3, 46.4)
    front = []
    for shoulder, hand, color in ((shoulder_l, hand_l, sleeve_l), (shoulder_r, hand_r, sleeve_r)):
        front.append(inked_line(shoulder, hand, color, 1.25))
        front.append(ellipse(hand[0], hand[1], 0.78, 0.7, skin["base"], stroke=INK, width=0.22))
    return "".join(front), hand_r, hand_l


def book_in_hands(spec):
    s = {"book": (spec["main"], spec["trim"])}
    return ua.book(s)


# --- weapons ----------------------------------------------------------------------

def weapon(spec, hand_r, hand_l):
    """(behind the body, in front) for the chosen weapon."""
    kind = spec["weapon"]
    hx, hy = hand_r
    if kind == "none":
        return "", ""
    if kind in ("sword", "sword_shield"):
        tip = (hx + 3.6, hy - 9.5)
        blade = "".join([
            inked_line((hx, hy), tip, STEEL["base"], 0.75, cap="butt"),
            line((hx + 0.25, hy - 0.8), (tip[0] - 0.1, tip[1] + 0.6), STEEL["light"], 0.2),
            poly([tip, (tip[0] + 0.55, tip[1] + 0.9), (tip[0] - 0.45, tip[1] + 1.1)], STEEL["base"], width=0.16),
            inked_line((hx - 1.1, hy + 0.5), (hx + 1.0, hy - 0.4), GOLD["base"], 0.45),
            inked_line((hx, hy), (hx - 0.35, hy + 1.3), WOOD["base"], 0.5),
        ])
        if kind == "sword_shield":
            return "", blade + shield(hand_l, spec)
        return "", blade
    if kind == "spear":
        return "", "".join([
            ua.wood_beam((hx + 0.4, hy + 6.5), (hx - 0.6, hy - 17), 0.75),
            poly([(hx - 0.7, hy - 20.2), (hx + 0.05, hy - 16.8), (hx - 1.25, hy - 16.9)], STEEL["base"], width=0.2),
        ])
    if kind == "shield":
        return "", shield(hand_l, spec)
    if kind == "bow":
        lx, ly = hand_l
        return "", "".join([
            path(f"M {lx + 0.2:.2f} {ly - 6.4:.2f} Q {lx - 3.4:.2f} {ly:.2f} {lx + 0.2:.2f} {ly + 6.4:.2f}", stroke=INK, width=0.95 + INK_W * 2),
            path(f"M {lx + 0.2:.2f} {ly - 6.4:.2f} Q {lx - 3.4:.2f} {ly:.2f} {lx + 0.2:.2f} {ly + 6.4:.2f}", stroke=WOOD["base"], width=0.95),
            line((lx + 0.2, ly - 6.4), (lx + 0.2, ly + 6.4), "#e8e2d0", 0.12),
        ])
    if kind == "sling":
        return "", "".join([
            path(f"M {hx:.2f} {hy:.2f} Q {hx + 2.4:.2f} {hy + 2.2:.2f} {hx + 1.2:.2f} {hy + 4.2:.2f}", stroke="#8a5a1a", width=0.3),
            ellipse(hx + 1.2, hy + 4.4, 0.75, 0.6, "#8a5a1a", stroke=INK, width=0.16),
            ellipse(hx + 1.1, hy + 4.3, 0.36, 0.32, "#9aa4b0"),
        ])
    # The original units' props, drawn where their hand would be.
    props = {"staff": ua.prop_staff, "club": ua.prop_club, "keys": ua.prop_keys, "chalice": ua.prop_chalice,
             "cross_staff": ua.prop_cross_staff, "knife": ua.prop_knife, "purse": ua.prop_purse, "saw": ua.prop_saw,
             "halberd": ua.prop_halberd}
    if kind in props:
        dx, dy = hx - 38.6, hy - 45.0
        return "", f'<g transform="translate({dx:.2f} {dy:.2f})">{props[kind]()}</g>'
    return "", ""


def shield(hand_l, spec):
    lx, ly = hand_l
    base, shade = CLOTH[spec["cape_color"]] if spec["cape"] != "none" else ("#b91c1c", "#7f1d1d")
    x0, y0 = lx - 2.6, ly - 4.6
    return "".join([
        path(f"M {x0:.2f} {y0:.2f} Q {x0 + 2.2:.2f} {y0 - 1:.2f} {x0 + 4.4:.2f} {y0:.2f} L {x0 + 4.4:.2f} {y0 + 7.6:.2f} "
             f"Q {x0 + 2.2:.2f} {y0 + 8.8:.2f} {x0:.2f} {y0 + 7.6:.2f} Z", fill=base),
        path(f"M {x0 + 2.2:.2f} {y0 - 0.5:.2f} L {x0 + 2.2:.2f} {y0 + 8.3:.2f}", stroke=shade, width=0.3),
        ellipse(x0 + 2.2, y0 + 3.8, 0.85, 0.85, GOLD["base"], stroke=INK, width=0.18),
        path(f"M {x0 + 0.5:.2f} {y0 + 0.6:.2f} L {x0 + 0.5:.2f} {y0 + 7.0:.2f}", stroke=GOLD["light"], width=0.25, opacity=0.8),
    ])


# --- assembly ---------------------------------------------------------------------

def figure_svg(spec):
    spec = {**DEFAULT_SPEC, **spec}
    skin = SKINS[spec["skin"]]
    hair = HAIR_COLORS[spec["hair_color"]]
    arm_front, hand_r, hand_l = arms(spec, skin)
    weapon_back, weapon_front = weapon(spec, hand_r, hand_l) if spec["arms"] != "book" else ("", "")
    back_hair, scalp = hair_parts(spec, hair)
    if spec["helmet"] in ("legionary", "centurion", "hood", "headwrap"):
        scalp = ""  # covered
        if spec["helmet"] != "hood":
            back_hair = ""
    head_faces, head_outline = head(spec, skin)
    transform = HEAD_TRANSFORMS.get(spec["head"], "")
    head_group = "".join([back_hair, beard(spec, hair), head_faces, face(spec, skin, hair), head_outline, scalp, helmet(spec)])
    if transform:
        head_group = f'<g transform="{transform}">{head_group}</g>'
    parts = [ua.stand(), cape(spec), weapon_back, legs(spec, skin), torso(spec), head_group, arm_front]
    if spec["arms"] == "book":
        parts += [book_in_hands(spec), ua.hands()]
    parts.append(weapon_front)
    view_x, view_y = -ua.ORIGIN_X / ua.FIGURE_SCALE, -ua.ORIGIN_Y / ua.FIGURE_SCALE
    view_w, view_h = ua.CANVAS_W / ua.FIGURE_SCALE, ua.CANVAS_H / ua.FIGURE_SCALE
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_x:.4f} {view_y:.4f} {view_w:.4f} {view_h:.4f}" '
            f'width="{ua.CANVAS_W}" height="{ua.CANVAS_H}">' + "".join(parts) + "</svg>")


# --- the donkey: a playable pack animal, drawn on the same stand and in the
# same chibi style as the people (big head, sparkly eyes), facing front-left.
DONKEY_COATS = {"grey": ("#9a8d80", "#6f6459"), "brown": ("#8a6a4e", "#62482f"), "dun": ("#b39a74", "#857150")}


def donkey_svg(coat="grey", pack="crimson"):
    base, shade = DONKEY_COATS[coat]
    pale = "#e6dccd"
    cloth, cloth_shade = CLOTH[pack]

    def tilted(svg, angle, x, y):
        return f'<g transform="rotate({angle} {x} {y})">{svg}</g>'
    parts = [ua.stand()]
    # Tail, then the far legs, in shadow behind the body.
    parts.append(path("M 40.8 43.6 Q 43.2 45.5 42.6 48.6", stroke=INK, width=0.9))
    parts.append(path("M 40.8 43.6 Q 43.2 45.5 42.6 48.6", stroke=shade, width=0.55))
    parts.append(ellipse(42.6, 49.1, 0.75, 1.1, "#3a2c22", stroke=INK, width=0.18))
    for x in (30.6, 39.0):
        parts.append(inked_line((x, 46.5), (x, 51.6), shade, 1.5, cap="butt"))
        parts.append(ellipse(x, 51.9, 0.95, 0.5, "#3a2c22", stroke=INK, width=0.18))
    # Body and belly.
    parts.append(ellipse(35, 44.6, 7.2, 4.4, base, stroke=INK, width=0.3))
    parts.append(ellipse(35.4, 46.6, 5.0, 1.9, pale, opacity=0.85))
    # Saddle bags with a rolled blanket on top.
    parts.append(poly([(32.2, 40.6), (38.4, 40.6), (38.9, 46.4), (31.7, 46.4)], cloth, width=0.25))
    parts.append(poly([(35.3, 40.6), (38.4, 40.6), (38.9, 46.4), (35.6, 46.4)], cloth_shade, stroke=None))
    parts.append(line((32.0, 43.2), (38.7, 43.2), "#f0d9a0", 0.35))
    parts.append(ellipse(35.3, 40.3, 3.6, 1.1, "#d9c49a", stroke=INK, width=0.22))
    # Near legs with dark hooves.
    for x in (29.0, 37.4):
        parts.append(inked_line((x, 46.8), (x, 52.4), base, 1.6, cap="butt"))
        parts.append(ellipse(x + 0.1, 52.7, 1.0, 0.55, "#2e231b", stroke=INK, width=0.18))
    # Neck and a short upright mane.
    parts.append(poly([(28.0, 40.0), (31.6, 41.2), (31.0, 46.0), (27.6, 45.0)], base, width=0.28))
    for i in range(5):
        x = 26.9 + i * 0.9
        parts.append(line((x, 33.4 + i * 1.3), (x + 0.7, 32.6 + i * 1.3), "#3a2c22", 0.6))
    # Long ears, pink inside.
    for x, angle in ((24.2, -18), (29.0, 16)):
        parts.append(tilted(ellipse(x, 30.6, 1.35, 3.6, base, stroke=INK, width=0.26), angle, x, 33.5))
        parts.append(tilted(ellipse(x, 30.9, 0.6, 2.5, "#e9a9a0"), angle, x, 33.5))
    # Head, muzzle, nostrils and a small smile.
    parts.append(ellipse(26.6, 36.0, 4.6, 3.9, base, stroke=INK, width=0.3))
    parts.append(ellipse(25.6, 39.2, 3.3, 2.2, pale, stroke=INK, width=0.25))
    for x in (24.5, 26.7):
        parts.append(ellipse(x, 38.8, 0.42, 0.3, "#4a3a30"))
    parts.append(path("M 24.6 40.2 Q 25.6 40.9 26.6 40.2", width=0.25))
    parts.append(ellipse(22.9, 37.6, 0.8, 0.45, "#f2a0a0", opacity=0.6))
    parts.append(ellipse(30.2, 37.6, 0.8, 0.45, "#f2a0a0", opacity=0.6))
    parts.append(cute_eye(24.6, 35.2, "#5a3a22", False, False))
    parts.append(cute_eye(28.6, 35.2, "#5a3a22", False, True))
    # A forelock tuft between the ears.
    parts.append(path("M 25.6 32.6 Q 26.6 31.2 27.8 32.6", fill="#3a2c22", width=0.2))
    view_x, view_y = -ua.ORIGIN_X / ua.FIGURE_SCALE, -ua.ORIGIN_Y / ua.FIGURE_SCALE
    view_w, view_h = ua.CANVAS_W / ua.FIGURE_SCALE, ua.CANVAS_H / ua.FIGURE_SCALE
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_x:.4f} {view_y:.4f} {view_w:.4f} {view_h:.4f}" '
            f'width="{ua.CANVAS_W}" height="{ua.CANVAS_H}">' + "".join(parts) + "</svg>")


def render_donkey_png(out_path, coat="grey", pack="crimson"):
    ua.render_png(donkey_svg(coat, pack), out_path)


def render_rgba(spec, scale=ua.SUPERSAMPLE):
    """(width, height, straight-alpha RGBA bytes) for the figure."""
    import numpy as np
    import pymupdf
    page = pymupdf.open(stream=figure_svg(spec).encode("utf-8"), filetype="svg")[0]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=True)
    rgba = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 4).astype(np.float32)
    alpha = rgba[:, :, 3:4]
    rgba[:, :, :3] = np.where(alpha > 0, np.clip(rgba[:, :, :3] * 255 / np.maximum(alpha, 1), 0, 255), 0)
    return pix.width, pix.height, rgba.astype(np.uint8).tobytes()


def render_png(spec, out_path):
    """Writes the game-ready token (the same size as the other units')."""
    ua.render_png(figure_svg(spec), out_path)


ENEMY_LOOK = {"body": ["armor"], "helmet": ["legionary", "legionary", "centurion"], "legs": ["greaves", "sandals"],
              "weapon": ["sword", "spear", "sword_shield", "shield", "bow", "club"], "arms": ["hold", "hold", "raised"],
              "main": ["crimson", "crimson", "brown"], "cape": ["none", "short", "long"], "cape_color": ["crimson"]}
PERSON_LOOK = {"body": ["robe", "tunic", "toga"], "helmet": ["none", "none", "none", "hood", "headwrap", "laurel"],
               "legs": ["robe", "sandals", "trousers"], "weapon": ["none", "staff", "keys", "chalice", "purse", "cross_staff"],
               "arms": ["book", "sides", "hold", "raised"], "cape": ["none", "none", "short", "long"]}


def random_spec(kind="person", rng=random):
    """A random design - "person" (townsfolk, disciples) or "enemy" (soldiers)."""
    spec = {key: rng.choice(values) for key, values in OPTIONS.items()}
    look = ENEMY_LOOK if kind == "enemy" else PERSON_LOOK
    for key, values in look.items():
        spec[key] = rng.choice(values)
    if spec["weapon"] != "none" and spec["arms"] == "book":
        spec["arms"] = "hold"
    if spec.get("feminine"):
        spec["beard"] = "none"
    return spec

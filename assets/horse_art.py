"""Generates assets/horse.png: the mount drawn under a mounted unit's token
(see MOUNT_ART in scripts/game_logic.py), in the same flat, ink-outlined,
cel-shaded style as the unit art (assets/unit_art.py) - a bay horse in a
three-quarter side view, facing left, with a red saddle cloth where the
rider sits.

Drawn at SUPERSAMPLE times its final size and scaled down for smooth edges.

Run from the project root:  python assets/horse_art.py
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "horse.png")

W, H = 200, 150          # final size
SUPERSAMPLE = 4
INK = (43, 26, 18, 255)
COAT = (150, 92, 52, 255)
COAT_SHADE = (116, 68, 38, 255)
COAT_LIGHT = (184, 124, 76, 255)
MANE = (52, 34, 26, 255)
HOOF = (60, 48, 40, 255)
CLOTH = (176, 48, 44, 255)
CLOTH_TRIM = (232, 190, 90, 255)


def s(points):
    return [(x * SUPERSAMPLE, y * SUPERSAMPLE) for x, y in points]


def poly(d, points, fill, ink=4):
    d.polygon(s(points), fill=fill, outline=INK, width=ink)


def ellipse(d, box, fill, ink=4):
    x0, y0, x1, y1 = box
    d.ellipse([x0 * SUPERSAMPLE, y0 * SUPERSAMPLE, x1 * SUPERSAMPLE, y1 * SUPERSAMPLE], fill=fill, outline=INK, width=ink)


def leg(d, top, knee, hoof, fill):
    # A tapered leg: thigh to knee to fetlock, with a dark hoof.
    (tx, ty), (kx, ky), (hx, hy) = top, knee, hoof
    poly(d, [(tx - 9, ty), (tx + 9, ty), (kx + 5, ky), (hx + 4, hy - 6), (hx - 4, hy - 6), (kx - 5, ky)], fill)
    poly(d, [(hx - 6, hy - 7), (hx + 6, hy - 7), (hx + 7, hy), (hx - 7, hy)], HOOF)


def main():
    img = Image.new("RGBA", (W * SUPERSAMPLE, H * SUPERSAMPLE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Far legs first, in shade.
    leg(d, (62, 92), (60, 116), (58, 140), COAT_SHADE)
    leg(d, (136, 92), (142, 116), (138, 140), COAT_SHADE)
    # Tail, sweeping down behind the rump.
    poly(d, [(160, 70), (178, 78), (186, 112), (176, 126), (170, 100), (158, 84)], MANE)
    # Body and rump.
    ellipse(d, (44, 56, 170, 106), COAT)
    ellipse(d, (120, 58, 172, 104), COAT)
    # Belly shade and a highlight along the back, cel style.
    d.chord(s([(50, 76), (166, 110)])[0] + s([(50, 76), (166, 110)])[1], 20, 160, fill=COAT_SHADE)
    d.chord(s([(62, 58), (156, 80)])[0] + s([(62, 58), (156, 80)])[1], 200, 340, fill=COAT_LIGHT)
    # Neck and head, reaching up and forward to the left.
    poly(d, [(64, 70), (40, 30), (54, 22), (86, 64)], COAT)
    poly(d, [(40, 30), (18, 42), (12, 54), (22, 58), (40, 48), (56, 34), (54, 22)], COAT)
    ellipse(d, (10, 48, 24, 60), COAT_SHADE, ink=3)          # muzzle
    poly(d, [(46, 22), (48, 10), (54, 20)], COAT)             # ear
    d.ellipse(s([(33, 34), (37, 38)])[0] + s([(33, 34), (37, 38)])[1], fill=INK)  # eye
    # Mane along the top of the neck.
    poly(d, [(52, 20), (60, 22), (90, 62), (80, 64), (70, 50), (62, 40)], MANE)
    # Near legs, over the body.
    leg(d, (72, 94), (74, 118), (72, 142), COAT)
    leg(d, (146, 94), (150, 118), (146, 142), COAT)
    # Saddle cloth where the rider sits, with a gold trim.
    poly(d, [(84, 56), (128, 56), (132, 90), (80, 90)], CLOTH)
    d.line(s([(81, 86), (131, 86)]), fill=CLOTH_TRIM, width=4 * SUPERSAMPLE // 2)

    img.resize((W, H), Image.LANCZOS).save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()

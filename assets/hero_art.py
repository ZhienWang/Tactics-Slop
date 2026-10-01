"""Generates the hero's on-map tokens, one per class role -
assets/hero_analyst.png, hero_diplomat.png, hero_sentinel.png and
hero_explorer.png - from Mark's token (assets/mark.png), recolouring its
blue stand and its green book to the role's colour (see ROLE_COLORS in
scripts/hero.py), so the hero reads apart from Mark at a glance.

Run from the project root:  python assets/hero_art.py
"""
import colorsys
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from scripts.hero import ROLE_COLORS  # noqa: E402

SOURCE = os.path.join(HERE, "mark.png")
# The source's blue stand and green book - the parts that take the role colour.
RECOLOR_HUES = ((0.52, 0.68), (0.33, 0.47))


def recolor(img, rgb):
    target_h, target_s, _ = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if not a:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if s > 0.3 and any(low <= h <= high for low, high in RECOLOR_HUES):
                nr, ng, nb = colorsys.hsv_to_rgb(target_h, min(1.0, s * (0.6 + target_s * 0.5)), v)
                px[x, y] = (round(nr * 255), round(ng * 255), round(nb * 255), a)
    return out


def main():
    source = Image.open(SOURCE).convert("RGBA")
    for role, rgb in ROLE_COLORS.items():
        path = os.path.join(HERE, f"hero_{role.lower()}.png")
        recolor(source, rgb).save(path)
        print("wrote", path)


if __name__ == "__main__":
    main()

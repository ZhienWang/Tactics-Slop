"""Generates the art a Legionnaire switches to once converted to the Player
side, from the regular Legionnaire token (assets/legionaire.png):

- assets/legionaire_converted.png: the on-map token, its red crest and
  shield recoloured Player blue, with a gold halo over the helmet.
- assets/portraits/legionaire_converted.png: the face portrait used by the
  HUD (turn order, profile box, action menu) - the same figure close up,
  lit warm from above against a dark backdrop, like the painted portraits.

Run from the project root:  python assets/converted_art.py
"""
import colorsys
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "legionaire.png")
TOKEN_OUT = os.path.join(HERE, "legionaire_converted.png")
PORTRAIT_OUT = os.path.join(HERE, "portraits", "legionaire_converted.png")

# Player blue, as a hue (0..1) the red parts are rotated onto.
PLAYER_HUE = 0.6
HALO = (255, 214, 110)


def is_red(r, g, b, a):
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return a > 0 and s > 0.35 and (h < 0.06 or h > 0.94)


def recolor_red_to_blue(img):
    """Moves every clearly red pixel onto Player blue, keeping its shading."""
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if is_red(r, g, b, a):
                h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                nr, ng, nb = colorsys.hsv_to_rgb(PLAYER_HUE, s * 0.85, min(1.0, v * 1.05))
                px[x, y] = (round(nr * 255), round(ng * 255), round(nb * 255), a)
    return img


def crest_box(img):
    """Bounding box of the helmet's red crest - the red pixels in the top
    half of the source (the shield, also red, sits lower down)."""
    px = img.load()
    points = [(x, y) for y in range(img.height // 2) for x in range(img.width) if is_red(*px[x, y])]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def draw_halo(img, cx, cy, width, height, line):
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    box = [cx - width // 2, cy - height // 2, cx + width // 2, cy + height // 2]
    d.ellipse(box, outline=(*HALO, 255), width=line)
    soft = glow.filter(ImageFilter.GaussianBlur(line * 1.5))
    img.alpha_composite(soft)
    img.alpha_composite(glow)
    return img


HEADROOM = 14


def build_token(source, crest):
    token = recolor_red_to_blue(source.copy())
    # The canvas has no headroom above the helmet, so the figure is shifted
    # down a little to make room for the halo.
    shifted = Image.new("RGBA", token.size, (0, 0, 0, 0))
    shifted.alpha_composite(token.crop((0, 0, token.width, token.height - HEADROOM)), (0, HEADROOM))
    left, top, right, _ = crest
    return draw_halo(shifted, (left + right) // 2, top + HEADROOM - 5, round((right - left) * 0.9), 11, 3)


def build_portrait(token, crest):
    w, h = token.size
    portrait = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    # Dark warm backdrop, brighter behind the head, like a painted portrait.
    back = ImageDraw.Draw(portrait)
    for y in range(h):
        t = y / h
        back.line([(0, y), (w, y)], fill=(round(46 - 26 * t), round(36 - 20 * t), round(30 - 16 * t), 255))
    light = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(light).ellipse([w * 0.25, -h * 0.4, w * 0.75, h * 0.7], fill=(255, 220, 150, 70))
    portrait.alpha_composite(light.filter(ImageFilter.GaussianBlur(18)))
    # The figure close up: crop around the helmet and body, scale to fill.
    left, top, right, _ = crest
    cx, top = (left + right) // 2, top + HEADROOM - 12
    crop_w = int(w * 0.62)
    crop = token.crop((cx - crop_w // 2, max(0, top), cx + crop_w // 2, max(0, top) + crop_w // 2))
    crop = crop.resize((w, h), Image.LANCZOS)
    portrait.alpha_composite(crop)
    return portrait


def main():
    source = Image.open(SOURCE).convert("RGBA")
    crest = crest_box(source)
    token = build_token(source, crest)
    token.save(TOKEN_OUT)
    build_portrait(token, crest).save(PORTRAIT_OUT)
    print("wrote", TOKEN_OUT, "and", PORTRAIT_OUT)


if __name__ == "__main__":
    main()

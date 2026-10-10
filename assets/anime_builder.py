"""Editable anime figures: adult proportions, angular faces and inked cel shadows.

Uses the existing part vocabulary, so saved designs can be reopened unchanged.
The wide transparent canvas is the same size as other game tokens.
"""
import random
import figure_builder as fb
from unit_art import CLOTH, ellipse, line, mix, path, poly

INK = "#161b30"


def shape(d, fill="none", width=0.32, stroke=INK):
    return path(d, fill=fill, stroke=stroke, width=width)


def head(spec, skin, hair):
    # Coordinates local to a seven-head-tall figure; each choice changes art.
    width = {"round": 1.04, "oval": 0.91, "wide": 1.15, "heart": 0.98, "small": 0.85}[spec["head"]]
    chin = 1.1 if spec["head"] == "heart" else 2.0
    parts = [
        shape(f"M -4.8 -2 Q -5.7 -8 0 -9 Q 5.5 -8 5 -2 L 4 3 L {chin} 5.5 L 0 6.5 L -3.8 3 Z", skin["base"]),
        shape("M 1 -8 Q 5 -7 5 -2 L 4 3 L 0 6.5 L -1 3 L 1 1 Z", skin["shade"], stroke=None),
        ellipse(-5, 0.5, 0.85, 1.5, skin["base"], stroke=INK, width=0.25),
        shape("M -5.1 0 L -4.7 1", skin["shade"], width=0.2),
        shape("M 0.3 -0.4 L -0.4 1.8 L 0.6 2.1", width=0.23),
    ]
    for x in (-2.5, 2.2):
        if spec["eyes"] == "closed":
            parts.append(shape(f"M {x-1.4} -0.1 Q {x} -1 {x+1.3} -0.1", width=0.35))
            continue
        opening = 0.4 if spec["eyes"] == "narrow" else 0.85
        parts += [shape(f"M {x-1.5} -0.5 Q {x-0.2} -1.6 {x+1.3} -0.6 Q {x+0.1} {opening} {x-1.5} -0.5 Z", "#f8edd4", width=0.22),
                  ellipse(x + 0.1, -0.35, 0.58, opening, fb.IRISES[spec["iris"]], stroke=INK, width=0.16),
                  ellipse(x + 0.18, -0.4, 0.22, opening * 0.8, INK),
                  ellipse(x - 0.1, -0.65, 0.16, 0.18, "#fff4df"),
                  shape(f"M {x-1.6} -0.5 Q {x} -1.7 {x+1.4} -0.6", width=0.4)]
        brow = -1.9 if spec["eyes"] == "fierce" else -2.4
        parts.append(shape(f"M {x-1.5} -2.7 L {x+1.2} {brow}", width=0.35))
        if spec["feminine"]:
            parts.append(shape(f"M {x-1.4} -0.6 L {x-1.9} -1.4", width=0.22))
    mouths = {"smile": "M -1.4 3.3 Q 0 4.3 1.4 3.1", "cat": "M -1.5 3.3 Q -0.8 4.1 0 3.4 Q 0.7 4.1 1.5 3.3",
              "neutral": "M -1.2 3.5 L 1.1 3.4", "frown": "M -1.3 3.8 Q 0 2.8 1.2 3.7",
              "open": "M -1.1 3.1 Q 0 2.8 1.1 3.1 L 0.8 4.2 Q 0 4.6 -0.8 4.2 Z"}
    parts.append(shape(mouths[spec["mouth"]], "#783e36" if spec["mouth"] == "open" else "none", width=0.22))
    beard = spec["beard"]
    if beard in ("full", "pointed"):
        tip = 9 if beard == "pointed" else 7
        parts.append(shape(f"M -4 1.9 L -2.8 3.3 L -1 3 L 0 3.6 L 1.3 3 L 3.8 1.7 L 3.4 5.3 L 0 {tip} L -3.3 5.1 Z", hair["base"], width=0.2))
        for x in (-2, -1, 1, 2):
            parts.append(shape(f"M {x} 4.6 L {x*0.65} {tip-0.8}", width=0.12, stroke=hair["light"]))
    elif beard == "mustache":
        parts.append(shape("M 0 2.4 Q -1 2 -2 3.5 L 0 3 Q 1.2 3.6 2 3.3 Q 1 2 0 2.4 Z", hair["base"], width=0.2))
    elif beard == "stubble":
        for x, y in ((-3, 3), (-2.4, 4), (-1.5, 5), (0, 5.7), (1.5, 5), (2.8, 4)):
            parts.append(line((x, y), (x + 0.3, y - 0.5), hair["base"], 0.18))
    style = spec["hair"]
    if style == "bald":
        parts.append(shape("M -5 -2 L -4.5 -5 L -4 -2 L -4.5 1 Z", hair["base"], width=0.2))
    elif style != "none":
        fringe = {"short": "L 4 -5 L 3 -2 L 1 -4 L -1 -2 L -2 -4 L -4 -2",
                  "standard": "L 4 -5 Q 2 -2 0 0 L 1 -4 Q -1 -1 -3 0 L -2 -4 L -4 0",
                  "long": "L 4 -3 L 1 -5 L 0 -3 L -2 -5 L -4 -2",
                  "flowing": "L 4 -3 L 2 -5 L 0 -2 L -1 -5 L -4 -1"}[style]
        parts.append(shape("M -5.2 1 L -5.5 -5 Q -6 -9 -2 -9.7 L -3 -11 Q 0 -10 1 -9.8 Q 5 -10 5.6 -6 L 5.4 2 L 4.5 3 " + fringe + " L -4.7 3 Z", mix(hair["base"], "#131c30", 0.35), width=0.28))
        for x in (-3, -1, 1, 3):
            parts.append(shape(f"M {x} -8.5 Q {x-1} -6 {x-2} -4", width=0.18, stroke=mix(hair["light"], "#24304d", 0.4)))
    # Existing helmet designs retain every accessory option, scaled to this head.
    parts.append(f'<g transform="scale(0.78 0.9) translate(-32 -35.2)">{fb.helmet(spec)}</g>')
    return f'<g transform="translate(85 18) scale({width * 0.8} 0.8)">{"".join(parts)}</g>'


def figure_svg(spec):
    spec = {**fb.DEFAULT_SPEC, **spec}
    skin = fb.SKINS[spec["skin"]]
    hair = fb.HAIR_COLORS[spec["hair_color"]]
    main, shade = CLOTH[spec["main"]]
    main, shade = mix(main, "#b5a184", 0.42), mix(shade, "#1e2945", 0.4)
    trim = mix(CLOTH[spec["trim"]][0], "#e4c38a", 0.15)
    parts = []
    if spec["cape"] != "none":
        base, dark = CLOTH[spec["cape_color"]]
        bottom = 75 if spec["cape"] == "long" else 51
        parts += [shape(f"M 76 27 Q 66 42 65 {bottom} L 80 {bottom-2} L 89 {bottom+2} L 104 {bottom-1} Q 102 45 94 27 Z", mix(dark, "#172039", 0.25)),
                  shape(f"M 94 29 Q 99 49 101 {bottom-2} L 94 {bottom-4} L 90 33 Z", base, stroke=None)]
    if spec["hair"] in ("long", "flowing"):
        bottom = 48 if spec["hair"] == "long" else 35
        parts.append(shape(f"M 80 12 Q 77 23 74 {bottom} L 80 {bottom-4} L 87 {bottom} L 96 {bottom-2} Q 91 26 90 12 Z", hair["base"]))
    # Two legs and sandals with a slight stagger for a natural standing pose.
    for x, offset in ((80, 0), (90, -1)):
        leg_color = trim if spec["legs"] == "trousers" else skin["base"]
        parts.append(shape(f"M {x-3} 47 L {x+3} 47 L {x+2} {74+offset} L {x-2} {74+offset} Z", leg_color))
        parts.append(shape(f"M {x} 49 L {x+3} 49 L {x+2} {74+offset} L {x} {74+offset} Z", mix(leg_color, "#1e2945", 0.3), stroke=None))
        if spec["legs"] == "greaves":
            parts.append(shape(f"M {x-2.5} 61 L {x+2.5} 61 L {x+2} 73 L {x-2} 73 Z", "#b7b8b1"))
            parts.append(line((x-1, 62), (x-1, 71), "#eee1b8", 0.5))
        parts.append(shape(f"M {x-2} {73+offset} L {x+2} {73+offset} L {x+4} {77+offset} Q {x} {79+offset} {x-3} {77+offset} Z", "#70513b"))
        parts.append(line((x-2, 75+offset), (x+2, 76+offset), trim, 0.55))
    feminine = spec["feminine"]
    waist = 5 if feminine else 7
    hem = 73 if spec["body"] in ("robe", "toga") or spec["legs"] == "robe" else 50
    # Neck, chest and cloth silhouette; shadows are solid, painted-looking planes.
    parts.append(shape("M 82 22 L 88 22 L 89 28 L 85 32 L 80 28 Z", skin["base"]))
    outline = f"M 80 26 Q 77 27 75 28 Q 73 31 73 35 L {85-waist} 43 Q 77 58 73 {hem} Q 85 {hem+3} 98 {hem-1} Q 94 57 {85+waist} 43 L 97 34 Q 96 30 94 28 L 89 26 L 85 31 Z"
    parts.append(shape(outline, main))
    parts.append(shape(f"M 89 28 L 94 29 L 95 34 L {85+waist} 43 L 98 {hem-1} L 89 {hem+1} L 84 47 L 88 37 Z", shade, stroke=None))
    for x in (77, 81, 87, 92):
        parts.append(shape(f"M {85+(x-85)*0.45} 44 Q {x-1} 57 {x} {hem-1}", width=0.28, stroke=shade))
        parts.append(shape(f"M {x} {hem-1} Q {x+0.8} {hem-5} {x+0.3} {hem-10}", width=0.18, stroke=mix(main,"#eee0b5",0.35)))
    for d in ("M 77 30 Q 81 31 83 34", "M 80 32 L 83 36 L 79 37", "M 92 31 L 89 35 L 91 39",
              "M 78 40 L 83 41", "M 88 40 L 92 39", "M 78 46 Q 82 49 82 53"):
        parts.append(shape(d,width=0.18,stroke=shade))
    # Fine, reproducible pigment marks stay clipped to the cloth silhouette.
    rng = random.Random(73)
    marks = []
    for _ in range(450):
        x, y = rng.uniform(72,98), rng.uniform(27,hem+2)
        marks.append(line((x,y),(x+rng.uniform(0.1,0.5),y+rng.uniform(-0.3,0.3)),
                          shade if rng.random()<0.6 else "#e3c799",rng.uniform(0.07,0.16),opacity=0.18))
    parts.append(f'<defs><clipPath id="cloth"><path d="{outline}"/></clipPath></defs><g clip-path="url(#cloth)">{"".join(marks)}</g>')
    parts.append(shape("M 80 26 L 85 31 L 89 26", width=0.8, stroke=trim))
    if spec["body"] == "armor":
        parts.append(shape("M 76 28 L 81 27 L 85 31 L 89 27 L 94 28 L 93 42 Q 85 45 77 42 Z", "#ac874e"))
        for y in (32, 35, 38, 41):
            parts.append(shape(f"M 77 {y} Q 85 {y+2} 93 {y}", width=0.65, stroke="#e0bc73"))
        for x in (78, 81, 84, 87, 90):
            parts.append(shape(f"M {x} 43 L {x+2} 43 L {x+2} 50 L {x-1} 50 Z", "#73583d", width=0.2))
    elif spec["body"] == "toga":
        parts.append(shape(f"M 93 27 Q 88 37 75 46 L 74 {hem-2} L 80 {hem} Q 87 42 97 32 Z", trim))
    parts.append(shape(f"M {85-waist} 42 L {85+waist} 42 L {85+waist} 44 L {85-waist} 44 Z", "#5c4134", width=0.25))
    parts.append(poly([(84,42),(87,42),(87,44),(84,44)],trim,stroke=INK,width=0.2))
    # Arms use bent elbows; the four poses move both hands and their equipment.
    poses = {"sides": ((72,40),(73,49),(99,40),(98,49)),
             "hold": ((71,40),(72,46),(100,38),(103,43)),
             "book": ((71,38),(81,40),(99,38),(89,40)),
             "raised": ((70,40),(71,48),(103,30),(104,23))}
    el, hl, er, hr = poses[spec["arms"]]
    for shoulder, elbow, hand, color in (((76,30),el,hl,main),((94,30),er,hr,shade)):
        # Round inked strokes form bent limbs without paper-thin horizontal arms.
        for a,b,fill,w in ((shoulder,elbow,color,4.6),(elbow,hand,skin["base"],2.7)):
            parts.append(line(a,b,INK,w+0.6))
            parts.append(line(a,b,fill,w))
            parts.append(line((a[0]+0.6,a[1]+0.3),(b[0]+0.6,b[1]+0.3),mix(fill,"#18253b",0.28),w*0.32))
        parts.append(ellipse(hand[0],hand[1],1.4,1.8,skin["base"],stroke=INK,width=0.25))
        for offset in (-0.5,0.2,0.8):
            parts.append(line((hand[0]+offset,hand[1]+0.6),(hand[0]+offset,hand[1]+1.3),skin["edge"],0.13))
    parts.append(head(spec,skin,hair))
    if spec["arms"] == "book":
        parts.append(shape("M 78 38 L 85 40 L 92 38 L 92 45 L 85 47 L 78 45 Z", trim))
        parts.append(shape("M 79 38 L 85 40 L 91 38 L 91 44 L 85 46 L 79 44 Z", "#ece0bc", width=0.22))
        parts.append(line((85,40),(85,46),INK,0.25))
    elif spec["weapon"] != "none":
        weapon_scale = 0.85 if spec["arms"] == "raised" else 1.7
        # Reuse the established inventory silhouettes, anchored to the new hands.
        back, front = fb.weapon(spec,(38.6,45),(26.8,46))
        # Shield and bow are held in the left hand; other equipment in the right.
        if spec["weapon"] == "sword_shield":
            sword = fb.weapon({**spec,"weapon":"sword"},(38.6,45),(26.8,46))[1]
            shield = fb.shield((26.8,46),spec)
            parts.append(f'<g transform="translate({hr[0]} {hr[1]}) scale({weapon_scale}) translate(-38.6 -45)">{sword}</g>')
            parts.append(f'<g transform="translate({hl[0]} {hl[1]}) scale({weapon_scale}) translate(-26.8 -46)">{shield}</g>')
        else:
            left = spec["weapon"] in ("shield","bow")
            hand, anchor = (hl,(26.8,46)) if left else (hr,(38.6,45))
            parts.append(f'<g transform="translate({hand[0]} {hand[1]}) scale({weapon_scale}) translate(-{anchor[0]} -{anchor[1]})">{back}{front}</g>')
    return '<svg xmlns="http://www.w3.org/2000/svg" width="170" height="85" viewBox="0 0 170 85">' + "".join(parts) + '</svg>'


def render_rgba(spec, scale=2):
    import numpy as np
    import pymupdf
    with pymupdf.open(stream=figure_svg(spec).encode(), filetype="svg") as doc:
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=True)
        rgba = np.frombuffer(pix.samples, np.uint8).reshape(pix.height,pix.width,4).astype(np.float32)
        alpha = rgba[:,:,3:4]
        rgba[:,:,:3] = np.where(alpha > 0, np.clip(rgba[:,:,:3]*255/np.maximum(alpha,1),0,255),0)
        return pix.width,pix.height,rgba.astype(np.uint8).tobytes()


def render_png(spec, out_path):
    from unit_art import render_png as save_svg
    save_svg(figure_svg(spec),out_path)

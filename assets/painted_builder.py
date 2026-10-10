"""Mix painted, transparent part layers using the original generator vocabulary."""
from functools import lru_cache
from pathlib import Path

import numpy as np
import pygame
import figure_builder as fb

PARTS = Path(__file__).parent / "anime" / "parts"
HEADS = ["round", "oval", "wide", "heart", "small"]
HAIR = ["standard", "short", "flowing", "long", "bald"]
BEARDS = ["full", "pointed", "mustache", "stubble"]
EYES = ["bright", "narrow", "fierce", "closed"]
MOUTHS = ["smile", "cat", "neutral", "frown", "open"]
EQUIPMENT = ["legionary", "centurion", "hood", "headwrap", "crown", "laurel",
             "sword", "spear", "shield", "sword_shield", "bow", "staff", "sling", "club",
             "keys", "chalice", "cross_staff", "knife", "purse", "saw", "halberd", "book"]
SCALE = 3


@lru_cache(maxsize=3)
def atlas(name):
    return pygame.image.load(str(PARTS / f"{name}.png"))


@lru_cache(maxsize=96)
def part(sheet, index):
    source = atlas(sheet)
    columns = 4 if sheet == "body" else 5
    row, col = divmod(index, columns)
    x0, x1 = col * source.get_width() // columns, (col+1) * source.get_width() // columns
    y0, y1 = row * source.get_height() // columns, (row+1) * source.get_height() // columns
    # The generated sheets preserve columns but allow tall parts more vertical
    # room. Explicit measured row bands avoid importing neighboring components.
    if sheet == "head":
        bands = [(0,307),(308,605),(632,860),(891,996),(1020,1235)]
        y0,y1 = bands[row]
        if index == 8:
            y0,y1 = 306,680
        elif index == 9:
            y0,y1 = 324,580
        elif index == 12:
            y0,y1 = 700,813
        elif index == 13:
            y0,y1 = 692,858
        elif index == 14:
            y0,y1 = 601,859
    elif sheet == "body":
        y0,y1 = [(0,324),(326,652),(654,919),(921,1254)][row]
        if index == 9:
            y1 = 854
        elif index == 13:
            y0 = 889
    image = source.subsurface((x0,y0,x1-x0,y1-y0))
    bounds = image.get_bounding_rect(min_alpha=40)
    if not bounds.width or not bounds.height:
        raise ValueError(f"Empty painted part: {sheet}/{index}")
    return image.subsurface(bounds).copy()


def rgb(color):
    return np.array(pygame.Color(color)[:3], dtype=np.float32)


def dye(image, material=None, color=None, trim=None):
    """Palette changes keep the painted luminance, alpha and ink contours."""
    image = image.copy()
    pixels = pygame.surfarray.pixels3d(image)
    source = pixels.astype(np.float32)
    red, green, blue = (source[:,:,i] for i in range(3))
    if material == "cloth":
        mask = (blue > red * 1.12) & (blue > green * 1.01) & (blue > 35)
        brightness = np.maximum(blue,green) / 155
    elif material == "skin":
        mask = (red > blue * 1.22) & (red > green * 1.04) & (red > 65)
        brightness = red / 255
    elif material == "hair":
        # Hair/beard layers can include ears or lip edges; leave those as skin.
        warm_skin = (red > blue * 1.3) & (red > green * 1.1) & (red > 65)
        mask = (np.maximum.reduce((red,green,blue)) > 24) & ~warm_skin
        brightness = np.maximum.reduce((red,green,blue)) / 100
    elif material == "iris":
        mask = (blue > red * 1.15) & (blue > green * 1.02) & (blue > 45)
        brightness = blue / 165
    else:
        mask = np.zeros(red.shape,dtype=bool)
        brightness = red * 0
    if color:
        # A small neutral highlight keeps texture readable in dark dyes.
        dyed = rgb(color)[None,None,:] * brightness[:,:,None]
        pixels[mask] = np.clip(dyed[mask],0,255).astype(np.uint8)
    if trim:
        belt = np.zeros(red.shape,dtype=bool)
        belt[:,int(image.get_height()*0.78):] = True
        belt &= (red > blue*1.2) & (red > 70)
        dyed = rgb(trim)[None,None,:] * (red/165)[:,:,None]
        pixels[belt] = np.clip(dyed[belt],0,255).astype(np.uint8)
    del pixels
    return image


def design_spec(design):
    """Old part designs keep every setting; temporary presets recover cast specs."""
    saved = design.get("spec", {})
    if "artwork" in saved:
        import json
        path = Path(__file__).parents[1] / "data" / "character_designs.json"
        with path.open(encoding="utf-8") as stream:
            original = json.load(stream).get(saved["artwork"], {}).get("spec", {})
        saved = original if "artwork" not in original else {}
    return {key: saved.get(key, default) if saved.get(key, default) in fb.OPTIONS[key] else default
            for key, default in fb.DEFAULT_SPEC.items()}


@lru_cache(maxsize=48)
def _figure(items):
    spec = {**fb.DEFAULT_SPEC, **dict(items)}
    canvas = pygame.Surface((340*SCALE,170*SCALE),pygame.SRCALPHA)
    skin = fb.SKINS[spec["skin"]]["base"]
    hair = fb.HAIR_COLORS[spec["hair_color"]]["base"]
    main = fb.CLOTH[spec["main"]][0]
    trim = fb.CLOTH[spec["trim"]][0]

    def put(sheet,index,box,material=None,color=None,trim_color=None,fit=False,crop=None):
        image = part(sheet,index)
        if crop:
            cx,cy,cw,ch = crop
            iw,ih = image.get_size()
            image = image.subsurface((round(cx*iw),round(cy*ih),max(1,round(cw*iw)),max(1,round(ch*ih)))).copy()
        if material == "hair":
            image = dye(image,"skin",skin)
        image = dye(image,material,color,trim_color)
        x,y,w,h = box
        if fit:
            ratio = min(w/image.get_width(),h/image.get_height())
            rw,rh = image.get_width()*ratio,image.get_height()*ratio
            x += (w-rw)/2
            w,h = rw,rh
        image = pygame.transform.smoothscale(image,(max(1,round(w*SCALE)),max(1,round(h*SCALE))))
        canvas.blit(image,(round(x*SCALE),round(y*SCALE)))

    if spec["cape"] != "none":
        long = spec["cape"] == "long"
        put("body",13 if long else 12,(124,44,92,112 if long else 67),"cloth",fb.CLOTH[spec["cape_color"]][0])
    # Back hair is painted as a wig with an empty face opening.
    if spec["hair"] in ("long","flowing"):
        hair_width = 78 if spec["hair"]=="long" else 62
        put("head",5+HAIR.index(spec["hair"]),(170-hair_width/2,17,hair_width,112 if spec["hair"]=="long" else 70),"hair",hair)
    lower = ["robe","sandals","greaves","trousers"].index(spec["legs"])
    if spec["body"] in ("robe","toga"):
        lower = 0 if spec["legs"] == "robe" else lower
    width = 57 if lower == 0 else 44
    put("body",4+lower,(170-width/2,91,width,67),"cloth",trim if lower==3 else main)
    if lower == 1:
        # Repaint the exposed skin without changing sandal leather.
        put("body",5,(148,91,44,67),"skin",skin)
    poses = {"sides": (8,(129,48,82,74)),"book":(9,(130,48,80,47)),
             "raised":(10,(129,21,82,100)),"hold":(11,(129,47,82,74))}
    arm_index, arm_box = poses[spec["arms"]]
    put("body",arm_index,arm_box,"skin",skin)
    torso = ["robe","tunic","armor","toga"].index(spec["body"])
    if spec["feminine"] and torso in (0,1):
        torso = 14+torso
    torso_width = 55 if spec["feminine"] else 65
    put("body",torso,(170-torso_width/2,43,torso_width,51),"cloth",main,trim)
    # Head and facial layers share anchors across all shapes.
    shape = HEADS.index(spec["head"])
    head_width = {"round":25,"oval":22,"wide":28,"heart":24,"small":21}[spec["head"]]
    put("head",14 if spec["feminine"] else shape,(170-head_width/2,18,head_width,29),"skin",skin)
    eye_index = 19 if spec["feminine"] and spec["eyes"] == "bright" else 15+EYES.index(spec["eyes"])
    # Features contain small skin edges; dye those before tinting the irises.
    features = dye(part("head",eye_index),"skin",skin)
    features = dye(features,"iris",fb.IRISES[spec["iris"]])
    features = pygame.transform.smoothscale(features,(round(head_width*.82*SCALE),round(5.5*SCALE)))
    canvas.blit(features,(round((170-head_width*.41)*SCALE),round(31*SCALE)))
    put("head",20+MOUTHS.index(spec["mouth"]),(166,39,8,3.8),"skin",skin)
    if spec["beard"] != "none":
        beard_height = {"full":13,"pointed":17,"mustache":4,"stubble":9}[spec["beard"]]
        put("head",10+BEARDS.index(spec["beard"]),(170-head_width*.43,38,head_width*.86,beard_height),"hair",hair)
    if spec["hair"] == "bald":
        put("head",9,(170-head_width*.66,21,head_width*.4,29),"hair",hair,crop=(0,0.25,0.3,0.7))
        put("head",9,(170+head_width*.26,21,head_width*.4,29),"hair",hair,crop=(0.7,0.25,0.3,0.7))
    elif spec["hair"] != "none":
        # Long styles share a fitted fringe over their separately painted back.
        index = 5 if spec["hair"] in ("long","flowing") else 5+HAIR.index(spec["hair"])
        put("head",index,(170-head_width*.66,14,head_width*1.32,35),"hair",hair)
    if spec["helmet"] != "none":
        tall = spec["helmet"] in ("legionary","centurion")
        h = 37 if tall else 30
        put("equipment",EQUIPMENT.index(spec["helmet"]),(151,12 if tall else 17,38,h),"cloth",main,fit=True)
    if spec["arms"] == "book":
        put("equipment",EQUIPMENT.index("book"),(150,80,40,23),fit=True)
    elif spec["weapon"] != "none":
        weapon = spec["weapon"]
        tall = weapon in ("spear","staff","cross_staff","halberd")
        shield = weapon in ("shield","sword_shield")
        height = 118 if tall else (56 if weapon in ("sword","bow","club") or shield else 27)
        x = 125 if shield or weapon == "bow" else 202
        width = 38 if shield else 27
        y = max(4,95-height*.68)
        put("equipment",EQUIPMENT.index(weapon),(x,y,width,height),fit=True)
    return canvas


def figure(spec):
    return _figure(tuple(sorted(spec.items()))).copy()


def token(spec,size):
    return pygame.transform.smoothscale(figure(spec),size)

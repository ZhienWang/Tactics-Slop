"""The hero's own look, chosen at a new game (scripts/hero_creator.py).

A look is a small dict saved in the profile: the face parts (the same ones
the character generator offers - head shape, skin, eyes, hair...), the
starting uniform picked from UNIFORMS, and its colour and trim. look_spec
turns it into a full figure_builder design, and hero_token draws it live -
the figure builder only builds the SVG, and pygame's own SVG loader
renders it, so this works in the browser build too. The drawn token is
registered under a made-up path (assets.register_image), so everything that
loads unit art by path - the battle, the world map, the result screen -
just finds it.
"""
import hashlib
import io
import json
import os
import sys

import pygame

from scripts.assets import register_image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "assets"))

import figure_builder as fb  # noqa: E402

TOKEN_SIZE = (340, 170)       # the same as every unit's token
FACE_KEYS = ["head", "skin", "eyes", "iris", "mouth", "hair", "hair_color", "beard", "feminine"]

# Starting uniforms: what the hero wears when the story begins. Each sets the
# clothes, what's in hand and what's on the head; the colour and trim are
# picked separately.
UNIFORMS = {
    "Pharisee's Robes": {"body": "robe", "legs": "robe", "arms": "book", "helmet": "headwrap", "cape": "long",
                         "cape_color": "white", "weapon": "none", "trim": "blue",
                         "blurb": "The long robes and blue-fringed mantle of a student of the Law."},
    "Temple Guard": {"body": "tunic", "legs": "sandals", "arms": "hold", "helmet": "headwrap", "cape": "short",
                     "cape_color": "slate", "weapon": "spear", "trim": "gold",
                     "blurb": "What the chief priests issue their guard: a belted tunic, a headwrap and a spear."},
    "Scribe": {"body": "tunic", "legs": "trousers", "arms": "book", "helmet": "none", "cape": "none",
               "cape_color": "brown", "weapon": "none", "trim": "brown",
               "blurb": "A copyist's plain tunic, ink on the fingers and a scroll always to hand."},
    "Fisherman": {"body": "tunic", "legs": "sandals", "arms": "sides", "helmet": "headwrap", "cape": "none",
                  "cape_color": "brown", "weapon": "none", "trim": "white",
                  "blurb": "A short work tunic, sleeves rolled, smelling faintly of the Sea of Galilee."},
    "Shepherd": {"body": "tunic", "legs": "sandals", "arms": "hold", "helmet": "hood", "cape": "short",
                 "cape_color": "brown", "weapon": "staff", "trim": "white",
                 "blurb": "A hooded wool cloak against the hill wind, and a staff for the flock."},
    "Traveller": {"body": "robe", "legs": "robe", "arms": "hold", "helmet": "hood", "cape": "long",
                  "cape_color": "brown", "weapon": "staff", "trim": "gold",
                  "blurb": "A dusty cloak and a walking staff - dressed for the long road."},
    "Tentmaker": {"body": "tunic", "legs": "trousers", "arms": "hold", "helmet": "none", "cape": "none",
                  "cape_color": "brown", "weapon": "knife", "trim": "brown",
                  "blurb": "A leather-worker's tunic, with the knife for cutting canvas tucked in the belt."},
    "Roman Citizen": {"body": "toga", "legs": "sandals", "arms": "sides", "helmet": "laurel", "cape": "none",
                      "cape_color": "crimson", "weapon": "none", "trim": "crimson",
                      "blurb": "A citizen's toga, worn with pride - and a citizenship that may yet save your life."},
}
UNIFORM_NAMES = list(UNIFORMS)
COLOURS = fb.OPTIONS["main"]
# A hero's starting colour follows their class's role (as hero tokens did).
ROLE_COLOURS = {"Analyst": "purple", "Diplomat": "green", "Sentinel": "blue", "Explorer": "gold"}

# The rows the creator shows: the face as in the character generator, then
# the uniform instead of the generator's body and accessory rows.
OPTIONS = {**{key: fb.OPTIONS[key] for key in FACE_KEYS}, "uniform": UNIFORM_NAMES, "main": COLOURS, "trim": COLOURS}


def default_look(role="Diplomat"):
    look = {key: fb.DEFAULT_SPEC[key] for key in FACE_KEYS}
    look.update(uniform="Traveller", main=ROLE_COLOURS.get(role, "blue"), trim=UNIFORMS["Traveller"]["trim"])
    return look


def random_look(rng, role="Diplomat"):
    base = fb.random_spec("person", rng)
    look = {key: base[key] for key in FACE_KEYS}
    uniform = rng.choice(UNIFORM_NAMES)
    look.update(uniform=uniform, main=rng.choice(COLOURS), trim=UNIFORMS[uniform]["trim"])
    if look["feminine"]:
        look["beard"] = "none"
    return look


def look_spec(look):
    """The full figure_builder design for a look."""
    uniform = UNIFORMS.get(look.get("uniform"), UNIFORMS["Traveller"])
    spec = dict(fb.DEFAULT_SPEC)
    spec.update({key: value for key, value in uniform.items() if key in fb.OPTIONS})
    spec.update({key: look[key] for key in FACE_KEYS if key in look})
    spec["main"] = look.get("main", spec["main"])
    spec["trim"] = look.get("trim", spec["trim"])
    return spec


def render_look(look, size=TOKEN_SIZE):
    """The look drawn as a token surface of `size`."""
    svg = fb.figure_svg(look_spec(look))
    return pygame.image.load_sized_svg(io.BytesIO(svg.encode("utf-8")), size)


def look_key(look):
    digest = hashlib.md5(json.dumps(look, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"hero_look/{digest}.png"


def hero_token(profile, role):
    """The path to load the hero's token from: their own look if they made
    one (drawn now and registered), otherwise their role's stock token."""
    look = (profile or {}).get("look")
    if not look:
        from scripts.hero import HERO_TOKEN
        return HERO_TOKEN.format(role=role.lower())
    key = look_key(look)
    register_image(key, render_look(look))
    return key

"""Painted anime art overrides; original assets remain available as fallbacks."""
import os

import pygame

ROOT = os.path.dirname(os.path.dirname(__file__))
ART_DIR = "assets/anime"


def character_art_path(path, face=False):
    key = os.path.splitext(os.path.basename(path or ""))[0]
    # Rank-and-file soldiers share role art, while named cast keep their identity.
    if key.startswith("legionnaire_shieldbearer") or key.startswith("legionnaire_sergeant"):
        key = "roman_shieldbearer"
    elif key.startswith("legionnaire_archer"):
        key = "roman_archer"
    elif key in ("centurion_marcus", "centurion_marcus_converted", "legionaire", "legionaire_converted"):
        key = "roman_centurion"
    candidate = f"{ART_DIR}/{'portraits' if face else 'units'}/{key}.png"
    return candidate if os.path.isfile(os.path.join(ROOT, candidate)) else None


def fit_art(image, size):
    """Keep natural figure proportions inside the engine's wide token slot."""
    scale = min(size[0] / image.get_width(), size[1] / image.get_height())
    scaled = pygame.transform.smoothscale(image, (max(1, round(image.get_width() * scale)),
                                                 max(1, round(image.get_height() * scale))))
    result = pygame.Surface(size, pygame.SRCALPHA)
    result.blit(scaled, scaled.get_rect(midbottom=(size[0] // 2, size[1])))
    return result

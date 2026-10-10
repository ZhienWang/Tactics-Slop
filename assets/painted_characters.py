"""The original painted character atlas, shared by previews and exports.

Read from the atlas rather than exported filenames so saving a character
with a cast member's name can never change the source artwork.
"""
from pathlib import Path
import pygame

KEYS = ["paul", "simon_peter", "john", "priscilla", "aquila", "barnabas",
        "timothy", "titus", "luke", "mark", "philip", "silas", "demas",
        "roman_centurion", "roman_shieldbearer", "roman_archer"]
PEOPLE = KEYS[:13]
ENEMIES = KEYS[13:]
_atlas = None
_figures = {}


def figure(key):
    global _atlas
    if key not in KEYS:
        raise ValueError(f"Unknown painted character: {key}")
    if key not in _figures:
        if _atlas is None:
            _atlas = pygame.image.load(str(Path(__file__).parent / "anime" / "character_atlas.png"))
        index = KEYS.index(key)
        col, row = index % 4, index // 4
        x0, x1 = col * _atlas.get_width() // 4, (col + 1) * _atlas.get_width() // 4
        y0, y1 = row * _atlas.get_height() // 4, (row + 1) * _atlas.get_height() // 4
        cell = _atlas.subsurface((x0, y0, x1-x0, y1-y0))
        _figures[key] = cell.subsurface(cell.get_bounding_rect(min_alpha=32)).copy()
    return _figures[key].copy()


def token(key, size):
    image = figure(key)
    factor = min(size[0]/image.get_width(), size[1]/image.get_height())
    image = pygame.transform.smoothscale(image, (max(1,round(image.get_width()*factor)),
                                                max(1,round(image.get_height()*factor))))
    result = pygame.Surface(size, pygame.SRCALPHA)
    result.blit(image, image.get_rect(midbottom=(size[0]//2,size[1])))
    return result

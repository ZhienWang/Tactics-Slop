"""Extract runtime assets from the generated, evenly spaced art atlases."""
from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parents[1] / "assets" / "anime"
CHARACTERS = ["paul", "simon_peter", "john", "priscilla", "aquila", "barnabas",
              "timothy", "titus", "luke", "mark", "philip", "silas", "demas",
              "roman_centurion", "roman_shieldbearer", "roman_archer"]
TERRAINS = ["moss", "dirt", "sand", "stone", "cobblestone", "wood", "water", "snow", "grass"]


def extract():
    for folder in ("units", "portraits", "terrain"):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    atlas = pygame.image.load(str(ROOT / "character_atlas.png"))
    for index, key in enumerate(CHARACTERS):
        col, row = index % 4, index // 4
        x0, x1 = col * atlas.get_width() // 4, (col + 1) * atlas.get_width() // 4
        y0, y1 = row * atlas.get_height() // 4, (row + 1) * atlas.get_height() // 4
        cell = atlas.subsurface((x0, y0, x1 - x0, y1 - y0)).copy()
        bounds = cell.get_bounding_rect(min_alpha=32)
        figure = cell.subsurface(bounds).copy()
        pygame.image.save(figure, str(ROOT / "units" / f"{key}.png"))
        # Bust crops keep faces large enough to read in the wide HUD slots.
        portrait = figure.subsurface((0, 0, figure.get_width(), max(1, round(figure.get_height() * 0.42)))).copy()
        backdrop = pygame.Surface(portrait.get_size())
        backdrop.fill((27, 37, 62))
        backdrop.blit(portrait, (0, 0))
        pygame.image.save(backdrop, str(ROOT / "portraits" / f"{key}.png"))
    terrain_path = ROOT / "terrain_atlas.png"
    if terrain_path.exists():
        atlas = pygame.image.load(str(terrain_path))
        for index, key in enumerate(TERRAINS):
            col, row = index % 3, index // 3
            x0, x1 = col * atlas.get_width() // 3, (col + 1) * atlas.get_width() // 3
            y0, y1 = row * atlas.get_height() // 3, (row + 1) * atlas.get_height() // 3
            cell = atlas.subsurface((x0, y0, x1 - x0, y1 - y0))
            pygame.image.save(pygame.transform.smoothscale(cell, (256, 256)), str(ROOT / "terrain" / f"{key}.png"))


if __name__ == "__main__":
    extract()

"""Effect gallery: every effect in data/effects.csv looping in a grid, so
you can pick one to bind in data/skill_effects.csv and tune its numbers.

Run from the project root:   python -m scripts.effects_gallery
  - Left/Right (or mouse wheel): page through the effects
  - 1-6: show one category (buff, curse, holy, first_aid, flash) / 0: all
  - Click a cell: play that effect large in the middle
  - F5: reload effects.csv (edit, save, press F5 to see the change)
  - Esc: quit
"""
import sys

import pygame

from scripts.config import SCREEN_WIDTH, SCREEN_HEIGHT
from scripts.data_editor import load_effects_from_csv
from scripts.effects import EffectManager, EffectSpec
from scripts.assets import get_font

COLS, ROWS = 8, 4
CATEGORIES = ["buff", "curse", "holy", "first_aid", "flash"]


def load_specs():
    return {name: EffectSpec(row) for name, row in load_effects_from_csv().items()}


def cycle_ms(specs, name, seen=None):
    """How long an effect (with its layers) runs, plus a short pause."""
    seen = seen or set()
    spec = specs[name]
    longest = spec.duration
    for layer in spec.layers:
        if layer in specs and layer not in seen:
            longest = max(longest, cycle_ms(specs, layer, seen | {name}) - 500)
    return longest + 500


def draw_tile(surface, cx, cy, zoom=1.0):
    w, h = 64 * zoom, 32 * zoom
    top = [(cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2), (cx - w / 2, cy)]
    pygame.draw.polygon(surface, (62, 70, 84), top)
    pygame.draw.polygon(surface, (96, 106, 124), top, 1)
    # A simple standee so effects can be judged against a unit's size.
    pygame.draw.ellipse(surface, (40, 44, 56), (cx - 9 * zoom, cy - 4 * zoom, 18 * zoom, 8 * zoom))
    pygame.draw.rect(surface, (120, 128, 150), (cx - 6 * zoom, cy - 30 * zoom, 12 * zoom, 28 * zoom), border_radius=round(4 * zoom))
    pygame.draw.circle(surface, (236, 200, 160), (round(cx), round(cy - 38 * zoom)), round(8 * zoom))


def main(screenshot=None, category=None, page=0, focus=None, shot_ms=900):
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Effect Gallery")
    font, small = get_font(22), get_font(18)
    clock = pygame.time.Clock()
    specs = load_specs()

    def visible_names():
        names = [n for n, s in specs.items() if category is None or s.category == category]
        per_page = COLS * ROWS
        return names[page * per_page:(page + 1) * per_page], max(1, -(-len(names) // per_page))

    cell_w, cell_h = SCREEN_WIDTH // COLS, (SCREEN_HEIGHT - 40) // ROWS
    manager = EffectManager(specs, seed=1)
    big_manager = EffectManager(specs, seed=2)
    next_play = {}
    start = pygame.time.get_ticks()

    def cell_center(index):
        col, row = index % COLS, index // COLS
        return col * cell_w + cell_w // 2, 40 + row * cell_h + int(cell_h * 0.72)

    running = True
    while running:
        now = pygame.time.get_ticks()
        names, pages = visible_names()
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RIGHT, pygame.K_PAGEDOWN):
                    page = (page + 1) % pages
                elif event.key in (pygame.K_LEFT, pygame.K_PAGEUP):
                    page = (page - 1) % pages
                elif event.key == pygame.K_F5:
                    specs = load_specs()
                    manager.specs = big_manager.specs = specs
                elif pygame.K_0 <= event.key <= pygame.K_5:
                    index = event.key - pygame.K_0
                    category = None if index == 0 else CATEGORIES[index - 1]
                    page = 0
                manager.effects.clear()
                next_play.clear()
            elif event.type == pygame.MOUSEWHEEL:
                page = (page - event.y) % pages
                manager.effects.clear()
                next_play.clear()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                col, row = event.pos[0] // cell_w, (event.pos[1] - 40) // cell_h
                index = row * COLS + col
                if 0 <= index < len(names):
                    focus = names[index]
                    big_manager.effects.clear()
                    big_manager.play(focus, "big")

        # Replay each cell's effect as soon as its last run has finished.
        for index, name in enumerate(names):
            if now >= next_play.get(name, 0):
                manager.play(name, index)
                next_play[name] = now + cycle_ms(specs, name)

        screen.fill((24, 26, 34))
        header = f"EFFECT GALLERY  {category or 'all'}  page {page + 1}/{pages}   <- -> page | 0-5 category | click: enlarge | F5 reload"
        screen.blit(font.render(header, True, (220, 220, 230)), (12, 10))
        for index, name in enumerate(names):
            cx, cy = cell_center(index)
            draw_tile(screen, cx, cy)
            spec = specs[name]
            label = small.render(name, True, (230, 230, 240))
            screen.blit(label, label.get_rect(midtop=(cx, 40 + (index // COLS) * cell_h + 4)))
            tag = small.render(spec.category, True, (140, 150, 170))
            screen.blit(tag, tag.get_rect(midtop=(cx, 40 + (index // COLS) * cell_h + 22)))
        manager.draw(screen, lambda tile: cell_center(tile), 1.0, now)

        if focus:
            overlay = pygame.Surface((520, 420), pygame.SRCALPHA)
            overlay.fill((10, 10, 16, 230))
            ox, oy = SCREEN_WIDTH // 2 - 260, SCREEN_HEIGHT // 2 - 210
            screen.blit(overlay, (ox, oy))
            pygame.draw.rect(screen, (200, 180, 90), (ox, oy, 520, 420), 2)
            draw_tile(screen, ox + 260, oy + 320, 2.0)
            big_manager.draw(screen, lambda tile: (ox + 260, oy + 320), 2.0, now)
            if not big_manager.active:
                big_manager.play(focus, "big")
            title = font.render(f"{focus}  ({specs[focus].category})", True, (255, 230, 150))
            screen.blit(title, (ox + 12, oy + 10))
            screen.blit(small.render(specs[focus].description, True, (210, 210, 220)), (ox + 12, oy + 36))

        pygame.display.flip()
        if screenshot and now - start >= shot_ms:
            pygame.image.save(screen, screenshot)
            running = False
        clock.tick(60)
    pygame.quit()


if __name__ == "__main__":
    args = sys.argv[1:]
    shot = args[args.index("--shot") + 1] if "--shot" in args else None
    cat = args[args.index("--category") + 1] if "--category" in args else None
    pg = int(args[args.index("--page") + 1]) if "--page" in args else 0
    at = int(args[args.index("--at") + 1]) if "--at" in args else 900
    main(screenshot=shot, category=cat, page=pg, shot_ms=at)

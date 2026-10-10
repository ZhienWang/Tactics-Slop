"""Character generator with interchangeable painted anime parts.

Choose head shape, face, hair, skin, arms, torso, legs, colours and equipment.
The preview and export combine painted layers using the original part schema.
Randomize Person / Randomize Enemy roll complete editable designs.

Save writes:
  assets/anime/units/<name>.png      the anime token, the same size as every unit's
  assets/anime/portraits/<name>.png  the matching bust portrait
  data/character_designs.json        the design, so it can be reopened later

Use the PNG as a character's portrait_path in any stage's characters.csv.
Needs pygame and numpy - a desktop tool, not part of the game itself.

Run from the project root:   python tools/character_generator.py

Controls: click the arrows (or select a row with Up/Down and change it with
Left/Right); click the name box to type; the buttons along the bottom do the
rest.
"""
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "assets"))

import pygame  # noqa: E402

import figure_builder as fb  # noqa: E402
import painted_builder as art  # noqa: E402
from scripts.assets import get_font  # noqa: E402

WIDTH, HEIGHT = 1600, 900
OUT_DIR = os.path.join(ROOT, "assets", "anime", "units")
DESIGNS_PATH = os.path.join(ROOT, "data", "character_designs.json")

BG = (32, 30, 40)
PANEL = (22, 20, 30)
EDGE = (120, 96, 60)
GOLD = (255, 215, 110)
TEXT = (236, 230, 214)
DIM = (160, 152, 136)
ROW_SELECTED = (70, 54, 34)

# The rows, grouped under headings: (heading, [(spec key, label), ...]).
GROUPS = [
    ("Head", [("head", "Head shape"), ("skin", "Skin"), ("eyes", "Eyes"), ("iris", "Eye colour"),
              ("mouth", "Mouth"), ("hair", "Hair"), ("hair_color", "Hair colour"), ("beard", "Beard"),
              ("feminine", "Feminine look")]),
    ("Body", [("arms", "Arms"), ("body", "Body"), ("main", "Main colour"), ("trim", "Trim colour"), ("legs", "Legs")]),
    ("Accessories", [("helmet", "Helmet"), ("cape", "Cape"), ("cape_color", "Cape colour"), ("weapon", "Weapon")]),
]
OPTIONS = fb.OPTIONS
DEFAULT_SPEC = fb.DEFAULT_SPEC
ROWS = [key for _, rows in GROUPS for key, _ in rows]
LABELS = {key: label for _, rows in GROUPS for key, label in rows}


def pretty(value):
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value).replace("_", " ").title()


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "character"


def load_designs():
    try:
        with open(DESIGNS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_design(name, team, spec):
    """Writes the token PNG and records the design. Returns the PNG's
    project-relative path."""
    key = slug(name)
    os.makedirs(OUT_DIR, exist_ok=True)
    png = os.path.join(OUT_DIR, f"{key}.png")
    pygame.image.save(art.figure(spec), png)
    # Export the same renderer used by the live preview, including a HUD bust.
    token = pygame.image.load(png)
    bounds = token.get_bounding_rect(min_alpha=32)
    bust = token.subsurface((bounds.x, bounds.y, bounds.width, max(1, round(bounds.height * 0.42)))).copy()
    portrait = pygame.Surface(bust.get_size())
    portrait.fill((27, 37, 62))
    portrait.blit(bust, (0, 0))
    face_dir = os.path.join(ROOT, "assets", "anime", "portraits")
    os.makedirs(face_dir, exist_ok=True)
    pygame.image.save(portrait, os.path.join(face_dir, f"{key}.png"))
    designs = load_designs()
    designs[key] = {"name": name, "team": team, "portrait_path": f"assets/anime/units/{key}.png", "art_style": "painted_parts", "spec": spec}
    with open(DESIGNS_PATH, "w", encoding="utf-8") as f:
        json.dump(designs, f, indent=2)
    return designs[key]["portrait_path"]


def render_surface(spec, scale):
    return art.token(spec, (round(170 * scale), round(85 * scale)))


class Generator:
    def __init__(self):
        self.spec = dict(DEFAULT_SPEC)
        self.name = "New Character"
        self.team = "Person"
        self.selected = 0
        self.typing = False
        self.message = "Choose parts with the arrows, name your character, then Save."
        self.designs = load_designs()
        self.design_index = 0
        self.preview = self.small = None
        self.refresh()

    # --- state ---
    def refresh(self):
        self.preview = render_surface(self.spec, 6)
        self.small = render_surface(self.spec, 1)

    def step(self, key, direction):
        values = OPTIONS[key]
        index = values.index(self.spec[key]) if self.spec[key] in values else 0
        self.spec[key] = values[(index + direction) % len(values)]
        if key == "weapon" and self.spec["weapon"] != "none" and self.spec["arms"] == "book":
            self.spec["arms"] = "hold"
        self.refresh()

    def randomize(self, kind):
        self.spec = fb.random_spec(kind, random)
        self.team = "Enemy" if kind == "enemy" else "Person"
        self.message = f"Random {kind} - keep rolling, or tweak any part."
        self.refresh()

    def save(self):
        path = save_design(self.name.strip() or "Character", self.team, dict(self.spec))
        self.designs = load_designs()
        self.message = f"Saved {path} - use it as portrait_path in a characters.csv."

    def load_selected(self):
        if not self.designs:
            self.message = "No saved designs yet."
            return
        key = sorted(self.designs)[self.design_index % len(self.designs)]
        design = self.designs[key]
        self.spec = art.design_spec(design)
        self.name, self.team = design["name"], design.get("team", "Person")
        self.message = f"Loaded {design['name']}."
        self.refresh()

    # --- layout ---
    def layout(self):
        rects, y = {}, 70
        for heading, rows in GROUPS:
            rects[("heading", heading)] = pygame.Rect(30, y, 560, 30)
            y += 34
            for key, _ in rows:
                rects[key] = pygame.Rect(30, y, 560, 32)
                rects[(key, -1)] = pygame.Rect(330, y + 2, 34, 28)
                rects[(key, 1)] = pygame.Rect(552, y + 2, 34, 28)
                y += 36
            y += 8
        buttons = {
            "name": pygame.Rect(640, 690, 420, 46),
            "team": pygame.Rect(1076, 690, 180, 46),
            "person": pygame.Rect(640, 760, 230, 50),
            "enemy": pygame.Rect(884, 760, 230, 50),
            "reset": pygame.Rect(1128, 760, 128, 50),
            "save": pygame.Rect(1272, 760, 290, 50),
            "design_prev": pygame.Rect(1272, 690, 40, 46),
            "design_next": pygame.Rect(1522, 690, 40, 46),
            "design_load": pygame.Rect(1316, 690, 202, 46),
        }
        return rects, buttons

    # --- input ---
    def click(self, pos):
        rects, buttons = self.layout()
        self.typing = buttons["name"].collidepoint(pos)
        for key in ROWS:
            for direction in (-1, 1):
                if rects[(key, direction)].collidepoint(pos):
                    self.selected = ROWS.index(key)
                    self.step(key, direction)
                    return
            if rects[key].collidepoint(pos):
                self.selected = ROWS.index(key)
                return
        if buttons["team"].collidepoint(pos):
            self.team = "Person" if self.team == "Enemy" else "Enemy"
        elif buttons["person"].collidepoint(pos):
            self.randomize("person")
        elif buttons["enemy"].collidepoint(pos):
            self.randomize("enemy")
        elif buttons["reset"].collidepoint(pos):
            self.spec = dict(DEFAULT_SPEC)
            self.refresh()
        elif buttons["save"].collidepoint(pos):
            self.save()
        elif buttons["design_prev"].collidepoint(pos) or buttons["design_next"].collidepoint(pos):
            self.design_index += -1 if buttons["design_prev"].collidepoint(pos) else 1
        elif buttons["design_load"].collidepoint(pos):
            self.load_selected()

    def key(self, event):
        if self.typing:
            if event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.typing = False
            elif event.key == pygame.K_BACKSPACE:
                self.name = self.name[:-1]
            elif event.unicode and event.unicode.isprintable() and len(self.name) < 28:
                self.name += event.unicode
            return
        if event.key == pygame.K_UP:
            self.selected = (self.selected - 1) % len(ROWS)
        elif event.key == pygame.K_DOWN:
            self.selected = (self.selected + 1) % len(ROWS)
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.step(ROWS[self.selected], -1 if event.key == pygame.K_LEFT else 1)
        elif event.key == pygame.K_s and (event.mod & pygame.KMOD_CTRL):
            self.save()

    # --- drawing ---
    def button(self, screen, rect, label, font, active=False):
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(screen, ROW_SELECTED if hovered or active else PANEL, rect, border_radius=8)
        pygame.draw.rect(screen, GOLD if active else EDGE, rect, 2, border_radius=8)
        text = font.render(label, True, TEXT)
        screen.blit(text, text.get_rect(center=rect.center))

    def draw(self, screen):
        font, small, head = get_font(22), get_font(18), get_font(26, bold=True)
        screen.fill(BG)
        screen.blit(get_font(34, bold=True).render("Character Generator - Painted Anime", True, GOLD), (30, 18))
        rects, buttons = self.layout()
        for heading, rows in GROUPS:
            screen.blit(head.render(heading, True, GOLD), rects[("heading", heading)].topleft)
            for key, label in rows:
                rect = rects[key]
                if ROWS[self.selected] == key:
                    pygame.draw.rect(screen, ROW_SELECTED, rect, border_radius=6)
                screen.blit(font.render(label, True, TEXT), (rect.x + 10, rect.y + 4))
                for direction, glyph in ((-1, "<"), (1, ">")):
                    self.button(screen, rects[(key, direction)], glyph, font)
                value = font.render(pretty(self.spec[key]), True, GOLD)
                screen.blit(value, value.get_rect(center=((rects[(key, -1)].right + rects[(key, 1)].left) // 2, rect.centery)))

        # The big preview, and the figure at its in-game size on the right.
        stage = pygame.Rect(630, 70, 940, 600)
        pygame.draw.rect(screen, PANEL, stage, border_radius=12)
        pygame.draw.rect(screen, EDGE, stage, 2, border_radius=12)
        # Fit the actual figure, rather than assuming the old chibi crop.
        big = art.figure(self.spec)
        big = big.subsurface(big.get_bounding_rect(min_alpha=32))
        scale = min(600 / big.get_width(), 540 / big.get_height())
        big = pygame.transform.smoothscale(big, (round(big.get_width() * scale), round(big.get_height() * scale)))
        screen.blit(big, big.get_rect(center=(stage.x + 330, stage.centery + 20)))
        game_size = pygame.transform.smoothscale(self.small, (round(140 * 1.95), round(70 * 1.95)))
        box = pygame.Rect(stage.right - 300, stage.y + 20, 280, 160)
        pygame.draw.rect(screen, (60, 70, 60), box, border_radius=8)
        screen.blit(game_size, game_size.get_rect(center=box.center))
        screen.blit(small.render("In game", True, DIM), (box.x + 8, box.bottom + 4))

        # Name, team, saved designs, actions.
        pygame.draw.rect(screen, (14, 12, 20), buttons["name"], border_radius=8)
        pygame.draw.rect(screen, GOLD if self.typing else EDGE, buttons["name"], 2, border_radius=8)
        caret = "|" if self.typing and (pygame.time.get_ticks() // 500) % 2 else ""
        screen.blit(font.render(f"Name: {self.name}{caret}", True, TEXT), (buttons["name"].x + 12, buttons["name"].y + 11))
        self.button(screen, buttons["team"], f"Team: {self.team}", font, active=self.team == "Enemy")
        names = [self.designs[k]["name"] for k in sorted(self.designs)]
        shown = names[self.design_index % len(names)] if names else "(none saved)"
        self.button(screen, buttons["design_prev"], "<", font)
        self.button(screen, buttons["design_next"], ">", font)
        self.button(screen, buttons["design_load"], f"Load: {shown}"[:24], small)
        self.button(screen, buttons["person"], "Randomize Person", font)
        self.button(screen, buttons["enemy"], "Randomize Enemy", font)
        self.button(screen, buttons["reset"], "Reset", font)
        self.button(screen, buttons["save"], "Save (Ctrl+S)", font, active=True)
        screen.blit(small.render(self.message, True, DIM), (640, 830))
        screen.blit(small.render("Up/Down: pick a row   Left/Right: change it   Click the name box to type", True, DIM), (30, 860))


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Character Generator - The Road to Jerusalem")
    clock = pygame.time.Clock()
    gen = Generator()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                gen.click(event.pos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
                gen.step(ROWS[gen.selected], 1 if event.button == 5 else -1)
            elif event.type == pygame.KEYDOWN:
                gen.key(event)
        gen.draw(screen)
        pygame.display.flip()
        clock.tick(60)
    pygame.quit()


if __name__ == "__main__":
    main()

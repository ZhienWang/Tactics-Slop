"""The new game's character creator: how the hero looks, and the uniform
they start in.

Laid out like the character generator (tools/character_generator.py): rows
of options down the left, each changed with its arrows (or Up/Down to pick
a row, Left/Right to change it), and a large preview on the right with the
figure at its in-game size. The face rows are the generator's own; its body
and accessory rows give way to the starting uniforms (scripts/hero_look.py),
with a colour and trim for each.

Like every screen of the front door, it's its own small async loop so the
browser build keeps running.
"""
import random

import pygame

from scripts.assets import get_font
from scripts.config import SCREEN_HEIGHT, SCREEN_WIDTH
from scripts.hero_look import OPTIONS, UNIFORMS, default_look, random_look, render_look

GOLD = (255, 215, 110)
TEXT = (240, 232, 214)
DIM = (190, 180, 160)
ROW_SELECTED = (90, 68, 42)
WELL = (28, 22, 16)
EDGE = (150, 120, 80)

GROUPS = [
    ("Head", [("head", "Head shape"), ("skin", "Skin"), ("eyes", "Eyes"), ("iris", "Eye colour"),
              ("mouth", "Mouth"), ("hair", "Hair"), ("hair_color", "Hair colour"), ("beard", "Beard"),
              ("feminine", "Feminine look")]),
    ("Starting uniform", [("uniform", "Uniform"), ("main", "Colour"), ("trim", "Trim")]),
]
ROWS = [key for _, rows in GROUPS for key, _ in rows]
PANEL = pygame.Rect(60, 40, SCREEN_WIDTH - 120, SCREEN_HEIGHT - 80)
STAGE = pygame.Rect(700, 110, 780, 520)


def pretty(value):
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value).replace("_", " ").title() if "'" not in str(value) else str(value)


def layout():
    rects, y = {}, PANEL.y + 80
    for heading, rows in GROUPS:
        rects[("heading", heading)] = pygame.Rect(PANEL.x + 50, y, 560, 30)
        y += 36
        for key, _ in rows:
            rects[key] = pygame.Rect(PANEL.x + 50, y, 560, 34)
            rects[(key, -1)] = pygame.Rect(PANEL.x + 330, y + 3, 34, 28)
            rects[(key, 1)] = pygame.Rect(PANEL.x + 572, y + 3, 34, 28)
            y += 38
        y += 10
    buttons = {
        "random": pygame.Rect(STAGE.x, PANEL.bottom - 100, 240, 60),
        "reset": pygame.Rect(STAGE.x + 260, PANEL.bottom - 100, 160, 60),
        "done": pygame.Rect(STAGE.right - 300, PANEL.bottom - 100, 300, 60),
    }
    return rects, buttons


class Creator:
    def __init__(self, look, role):
        self.role = role
        self.look = dict(look or default_look(role))
        self.selected = 0
        self.refresh()

    def refresh(self):
        self.preview = render_look(self.look, (1020, 510))
        self.small = render_look(self.look)

    def step(self, key, direction):
        values = OPTIONS[key]
        index = values.index(self.look[key]) if self.look.get(key) in values else 0
        self.look[key] = values[(index + direction) % len(values)]
        if key == "uniform":
            self.look["trim"] = UNIFORMS[self.look["uniform"]]["trim"]  # each uniform's own trim to start
        self.refresh()

    def click(self, pos):
        """Returns "done" when the player is finished."""
        rects, buttons = layout()
        for key in ROWS:
            for direction in (-1, 1):
                if rects[(key, direction)].collidepoint(pos):
                    self.selected = ROWS.index(key)
                    self.step(key, direction)
                    return None
            if rects[key].collidepoint(pos):
                self.selected = ROWS.index(key)
                return None
        if buttons["random"].collidepoint(pos):
            self.look = random_look(random, self.role)
            self.refresh()
        elif buttons["reset"].collidepoint(pos):
            self.look = default_look(self.role)
            self.refresh()
        elif buttons["done"].collidepoint(pos):
            return "done"
        return None

    def key(self, event):
        if event.key == pygame.K_UP:
            self.selected = (self.selected - 1) % len(ROWS)
        elif event.key == pygame.K_DOWN:
            self.selected = (self.selected + 1) % len(ROWS)
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.step(ROWS[self.selected], -1 if event.key == pygame.K_LEFT else 1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return "done"
        return None

    def draw(self, screen):
        surface = screen.surface
        font, small, head, title = get_font(24), get_font(20), get_font(28, bold=True), get_font(40, bold=True)
        screen.backdrop()
        screen.panel(PANEL)
        surface.blit(title.render("How do you look?", True, GOLD), (PANEL.x + 50, PANEL.y + 22))
        rects, buttons = layout()
        mouse = pygame.mouse.get_pos()
        for heading, rows in GROUPS:
            surface.blit(head.render(heading, True, GOLD), rects[("heading", heading)].topleft)
            for key, label in rows:
                rect = rects[key]
                if ROWS[self.selected] == key:
                    pygame.draw.rect(surface, ROW_SELECTED, rect, border_radius=6)
                surface.blit(font.render(label, True, TEXT), (rect.x + 10, rect.y + 5))
                for direction, glyph in ((-1, "<"), (1, ">")):
                    arrow = rects[(key, direction)]
                    hovered = arrow.collidepoint(mouse)
                    pygame.draw.rect(surface, ROW_SELECTED if hovered else WELL, arrow, border_radius=6)
                    pygame.draw.rect(surface, GOLD if hovered else EDGE, arrow, 2, border_radius=6)
                    text = font.render(glyph, True, TEXT)
                    surface.blit(text, text.get_rect(center=arrow.center))
                value = font.render(pretty(self.look[key]), True, GOLD)
                surface.blit(value, value.get_rect(center=((rects[(key, -1)].right + rects[(key, 1)].left) // 2, rect.centery)))

        # The big preview, the figure at its in-game size, and the uniform's story.
        pygame.draw.rect(surface, WELL, STAGE, border_radius=12)
        pygame.draw.rect(surface, EDGE, STAGE, 2, border_radius=12)
        big = self.preview.subsurface(pygame.Rect(170, 0, 680, 510))
        surface.blit(big, big.get_rect(center=(STAGE.x + 290, STAGE.centery + 6)))
        box = pygame.Rect(STAGE.right - 300, STAGE.y + 20, 280, 160)
        pygame.draw.rect(surface, (70, 110, 60), box, border_radius=8)
        game_size = pygame.transform.smoothscale(self.small, (round(140 * 1.95), round(70 * 1.95)))
        surface.blit(game_size, game_size.get_rect(center=box.center))
        surface.blit(small.render("In battle", True, DIM), (box.x + 8, box.bottom + 4))
        uniform = self.look["uniform"]
        blurb_top = box.bottom + 50
        surface.blit(head.render(uniform, True, GOLD), (box.x, blurb_top))
        words, line, y = UNIFORMS[uniform]["blurb"].split(), "", blurb_top + 40
        for word in words:
            trial = f"{line} {word}".strip()
            if small.size(trial)[0] > box.width:
                surface.blit(small.render(line, True, TEXT), (box.x, y))
                line, y = word, y + 26
            else:
                line = trial
        surface.blit(small.render(line, True, TEXT), (box.x, y))

        screen.button(buttons["random"], "Randomize", buttons["random"].collidepoint(mouse), font)
        screen.button(buttons["reset"], "Reset", buttons["reset"].collidepoint(mouse), font)
        screen.button(buttons["done"], "This is me", buttons["done"].collidepoint(mouse), head)
        hint = small.render("Up/Down: pick a row   Left/Right: change it   Enter: done", True, DIM)
        surface.blit(hint, (PANEL.x + 50, PANEL.bottom - 50))


async def look_screen(screen, look=None, role="Diplomat"):
    """Lets the player shape the hero. Returns the look (see hero_look)."""
    from scripts.intro import quit_game
    creator = Creator(look, role)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_game()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if creator.click(event.pos) == "done":
                    return creator.look
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
                creator.step(ROWS[creator.selected], 1 if event.button == 5 else -1)
            elif event.type == pygame.KEYDOWN and creator.key(event) == "done":
                return creator.look
        creator.draw(screen)
        await screen.flip()

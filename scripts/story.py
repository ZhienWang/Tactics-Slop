"""Visual-novel scenes: the story told around the battles.

A scene is a run of rows in data/story.csv (scene, when, command, who, text),
played in order:

  bg         text = "<sky>/<ground>" - a Skybox kind (see skybox.py) over a
             band of a terrain texture, e.g. "dawn/water" - or an image path
  show       who steps in at text = left | center | right
  hide       who steps out (a blank who clears everyone)
  say        who speaks text
  narrate    text, with no speaker
  title      a chapter card: who = small heading, text = title
  scripture  a verse card: who = reference, text = the verse
  reflect    the closing card: who = the passage to read, text = discussion
             questions split by |
  choice     who = prompt, text = options split by |; later rows whose `when`
             holds an option's number (1, 2, ...) only play if it was picked

"{hero}" in who or text becomes the player's name. Scripture is quoted from
the World English Bible (public domain).

A world map node's scenes are <node>_intro (before its battle, or the whole
story on a node without one) and <node>_outro (after a victory);
data/story_chapters.csv names each story and the passage it's drawn from.

Built on pygame rather than a separate VN engine so it runs in the pygbag
browser build like every other screen - its own small async loop, awaiting
asyncio.sleep(0) each frame. Click / Space / Enter advances (finishing a line
that's still typing first), Skip (or Esc) fast-forwards to the next choice or
closing card, and Log (or L, or the mouse wheel) shows the lines so far.
"""
import asyncio
import csv
import math
import os
import random
import sys
import zlib

import pygame

from scripts.assets import draw_nine_slice_panel, frame_content_rect, get_font, load_image_safe, load_nine_slice_frame
from scripts.config import SCREEN_HEIGHT, SCREEN_WIDTH
from scripts.hero import DEFAULT_HERO_NAME, HERO_FACE
from scripts.skybox import SKY_PROFILES, Skybox
from scripts.voices import DialogueVoice

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
STORY_PATH = os.path.join(DATA_DIR, "story.csv")
CHAPTERS_PATH = os.path.join(DATA_DIR, "story_chapters.csv")

BLOCKING = ("say", "narrate", "title", "scripture", "reflect", "choice")
COMMANDS = ("bg", "show", "hide") + BLOCKING
# Skip fast-forwards through everything but these - a choice needs the
# player, and the closing card is the point of the episode (Scripture first).
SKIP_STOPS = ("choice", "reflect")
SLOTS = {"left": 0.22, "center": 0.5, "right": 0.78}

TEXT = (240, 232, 214)
DIM = (190, 180, 160)
GOLD = (255, 215, 110)
NARRATION = (226, 208, 160)
BUTTON = (58, 44, 32)
BUTTON_HOVER = (96, 72, 46)
CARD_EDGE = (120, 96, 66)

TYPE_SPEED = 55  # characters per second
FADE_MS = 350
TEXT_BOX = pygame.Rect(140, SCREEN_HEIGHT - 250, SCREEN_WIDTH - 280, 225)
PORTRAIT_SIZE = (440, 220)
PORTRAIT_BOTTOM = TEXT_BOX.y - 40
GROUND_TOP = 0.6
LOG_BUTTON = pygame.Rect(SCREEN_WIDTH - 270, 20, 110, 44)
SKIP_BUTTON = pygame.Rect(SCREEN_WIDTH - 145, 20, 125, 44)
LOG_PANEL = pygame.Rect(160, 70, SCREEN_WIDTH - 320, SCREEN_HEIGHT - 140)

# Shown as a radiance rather than a face.
LIGHT_FIGURES = {"Jesus", "Angel"}
# Named characters without painted portraits get one of the converts' faces,
# always the same one for the same name (the hero's own face left out).
# Saul and Paul are the same man (Acts 13:9), so the same face.
PORTRAIT_ALIASES = {"Paul": "Saul"}
CONVERT_FACES = [path for path in (f"assets/portraits/converts/convert_{i:02d}.png" for i in range(1, 12)) if path != HERO_FACE]


def load_story(filepath=None):
    """{scene id: [row, ...]} in file order."""
    scenes = {}
    with open(filepath or STORY_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            scene = row["scene"].strip()
            if not scene:
                continue
            scenes.setdefault(scene, []).append({
                "command": row["command"].strip(),
                "who": (row.get("who") or "").strip(),
                "text": (row.get("text") or "").strip(),
                "when": (row.get("when") or "").strip(),
            })
    return scenes


def load_chapters(filepath=None):
    """The stories in order: [{chapter, node_id, title, passage}, ...]."""
    with open(filepath or CHAPTERS_PATH, newline="", encoding="utf-8") as f:
        chapters = [{"chapter": int(row["chapter"]), "node_id": row["node_id"].strip(),
                     "title": row["title"].strip(), "passage": row["passage"].strip()}
                    for row in csv.DictReader(f)]
    return sorted(chapters, key=lambda c: c["chapter"])


def scene_ids(node_id):
    """The (intro, outro) scene ids for a world map node."""
    return f"{node_id}_intro", f"{node_id}_outro"


def portrait_path(name):
    if name == "{hero}":
        return HERO_FACE
    name = PORTRAIT_ALIASES.get(name, name)
    slug = name.lower().replace(" ", "_")
    painted = f"assets/portraits/{slug}.png"
    if os.path.exists(os.path.join(ROOT, painted)):
        return painted
    return CONVERT_FACES[zlib.crc32(name.encode("utf-8")) % len(CONVERT_FACES)]


def ground_texture_path(name):
    """assets/<name>.png, or .jpg if that's what there is (e.g. grass)."""
    for ext in (".png", ".jpg"):
        if os.path.exists(os.path.join(ROOT, "assets", name + ext)):
            return f"assets/{name}{ext}"
    return None


def wrap(text, font, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if font.size(trial)[0] <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def quit_game():
    pygame.quit()
    sys.exit()


class Backdrop:
    """A procedural scene - a Skybox over a band of terrain texture - or a
    picture scaled to the screen."""

    def __init__(self, spec, seed=None):
        self.sky, self.ground, self.image = None, None, None
        sky_kind, _, ground = spec.partition("/")
        if sky_kind in SKY_PROFILES:
            self.sky = Skybox(sky_kind, SCREEN_WIDTH, SCREEN_HEIGHT, seed=seed or spec)
            self.ground = self._build_ground(ground, SKY_PROFILES[sky_kind], seed) if ground else None
        else:
            image = load_image_safe(spec)
            if image:
                self.image = pygame.transform.smoothscale(image, (SCREEN_WIDTH, SCREEN_HEIGHT))

    @staticmethod
    def _build_ground(name, profile, seed=None):
        """A band of ground in the terrain texture's own colour - the tiles
        are isometric diamonds, so they're not tiled flat - shaded toward the
        sky's ground haze (a night scene's ground is dark too), with
        horizontal streaks for depth (ripples on water, furrows on land)."""
        texture = load_image_safe(ground_texture_path(name))
        base = pygame.transform.average_color(texture, consider_alpha=True)[:3] if texture else profile["near"]
        base = tuple(round(b * 0.55 + g * 0.45) for b, g in zip(base, profile["ground"]))
        top = round(SCREEN_HEIGHT * GROUND_TOP)
        band = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT - top), pygame.SRCALPHA)
        height = band.get_height()
        feather = 60
        for y in range(height):
            t = y / height
            color = tuple(max(0, min(255, round(c * (1.15 - 0.55 * t)))) for c in base)
            pygame.draw.line(band, (*color, round(255 * min(1.0, y / feather))), (0, y), (SCREEN_WIDTH, y))
        rng = random.Random(f"{seed}/{name}")
        for _ in range(70):
            y = height * rng.random() ** 1.6  # bunched toward the horizon
            width = rng.randint(60, 260) * (0.4 + y / height)
            x = rng.uniform(-width, SCREEN_WIDTH)
            light = tuple(min(255, c + 40) for c in base)
            pygame.draw.ellipse(band, (*light, round(70 * min(1.0, y / feather))), (x, y, width, max(2, 6 * y / height)))
        return band

    def draw(self, surface):
        if self.image:
            surface.blit(self.image, (0, 0))
            return
        if self.sky:
            self.sky.draw(surface, 2, 0, 0)
        else:
            surface.fill((14, 11, 8))
        if self.ground:
            surface.blit(self.ground, (0, round(SCREEN_HEIGHT * GROUND_TOP)))


class StoryPlayer:
    def __init__(self, surface, rows, hero_name=None, seed=None):
        self.surface = surface
        self.rows = rows
        self.hero_name = hero_name or DEFAULT_HERO_NAME
        self.seed = seed
        self.index = 0
        self.choice = None
        self.backdrop = None
        self.cast = []  # [{"name", "slot", "since"}] in the order they stepped in
        self.step = None
        self.log = []
        self.log_open = False
        self.log_scroll = 0
        self.hover = None
        self.portraits = {}
        self.frame = load_nine_slice_frame([])
        self.voice = DialogueVoice()
        self.clock = pygame.time.Clock()

    # --- script ---

    def fill(self, value):
        return value.replace("{hero}", self.hero_name)

    def next_step(self):
        """Applies the instant rows (bg/show/hide) up to the next one that
        waits for the player, and returns that one - None at the end."""
        now = pygame.time.get_ticks()
        while self.index < len(self.rows):
            row = self.rows[self.index]
            self.index += 1
            if row["when"] and row["when"] != str(self.choice):
                continue
            command, who, text = row["command"], row["who"], self.fill(row["text"])
            if command == "bg":
                self.backdrop = Backdrop(text, seed=self.seed)
            elif command == "show":
                self.cast = [c for c in self.cast if c["name"] != who]
                self.cast.append({"name": who, "slot": text if text in SLOTS else "center", "since": now})
            elif command == "hide":
                self.cast = [c for c in self.cast if who and c["name"] != who]
            elif command in BLOCKING:
                step = {"command": command, "who": self.fill(who), "raw_who": who, "text": text, "start": now,
                        "typed": command not in ("say", "narrate")}
                if command == "choice":
                    step["options"] = [o.strip() for o in text.split("|") if o.strip()]
                    self.hover = 0
                if command in ("say", "narrate"):
                    self.log.append((step["who"] if command == "say" else "", text))
                return step
        return None

    def typing(self):
        if self.step is None or self.step["typed"]:
            return False
        shown = (pygame.time.get_ticks() - self.step["start"]) * TYPE_SPEED / 1000
        if shown >= len(self.step["text"]):
            self.step["typed"] = True
        return not self.step["typed"]

    def advance(self):
        if self.typing():
            self.step["typed"] = True
        elif self.step["command"] != "choice":
            self.step = self.next_step()

    def choose(self, index):
        self.choice = index + 1
        self.log.append(("", f"- {self.step['options'][index]}"))
        self.step = self.next_step()

    def skip(self):
        while self.step is not None and self.step["command"] not in SKIP_STOPS:
            self.step = self.next_step()

    # --- input ---

    def choice_rects(self):
        options = self.step["options"]
        top = TEXT_BOX.y - 40 - len(options) * 86
        return [pygame.Rect(SCREEN_WIDTH // 2 - 420, top + i * 86, 840, 70) for i in range(len(options))]

    def handle(self, event):
        if event.type == pygame.QUIT:
            quit_game()
        if self.log_open:
            if event.type == pygame.MOUSEWHEEL:
                self.log_scroll = max(0, self.log_scroll + event.y)
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_UP, pygame.K_DOWN):
                self.log_scroll = max(0, self.log_scroll + (1 if event.key == pygame.K_UP else -1))
            elif (event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_l, pygame.K_RETURN, pygame.K_SPACE)) \
                    or (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1):
                self.log_open = False
            return
        choosing = self.step["command"] == "choice"
        if event.type == pygame.MOUSEWHEEL and event.y > 0:
            self.log_open, self.log_scroll = True, 0
        elif event.type == pygame.MOUSEMOTION and choosing:
            self.hover = next((i for i, r in enumerate(self.choice_rects()) if r.collidepoint(event.pos)), self.hover)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if LOG_BUTTON.collidepoint(event.pos):
                self.log_open, self.log_scroll = True, 0
            elif SKIP_BUTTON.collidepoint(event.pos):
                self.skip()
            elif choosing:
                hit = next((i for i, r in enumerate(self.choice_rects()) if r.collidepoint(event.pos)), None)
                if hit is not None:
                    self.choose(hit)
            else:
                self.advance()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_l:
                self.log_open, self.log_scroll = True, 0
            elif event.key == pygame.K_ESCAPE:
                self.skip()
            elif choosing:
                count = len(self.step["options"])
                if event.key in (pygame.K_UP, pygame.K_w):
                    self.hover = (self.hover - 1) % count
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self.hover = (self.hover + 1) % count
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.choose(self.hover)
                elif pygame.K_1 <= event.key < pygame.K_1 + count:
                    self.choose(event.key - pygame.K_1)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                self.advance()

    # --- drawing ---

    def portrait(self, name):
        if name not in self.portraits:
            image = load_image_safe(portrait_path(name))
            self.portraits[name] = pygame.transform.smoothscale(image, PORTRAIT_SIZE) if image else None
        return self.portraits[name]

    def draw_light(self, rect, now, strength):
        """A figure of light in place of a face: a robed silhouette in a
        radiance, drawn straight onto the scene rather than in a card.
        `strength` (0-1) fades it in, and dims it while others speak."""
        size = rect.height * 2
        glow = pygame.Surface((size, size), pygame.SRCALPHA)
        pulse = (0.85 + 0.15 * math.sin(now / 420)) * strength
        c = size // 2
        for radius in range(c, 10, -5):
            alpha = round(120 * pulse * (1 - radius / c) ** 1.8)
            pygame.draw.circle(glow, (255, 238, 196, alpha), (c, c), radius)
        for i in range(16):
            angle = i * math.tau / 16 + now / 5000
            end = (c + math.cos(angle) * c, c + math.sin(angle) * c)
            pygame.draw.line(glow, (255, 236, 180, round(34 * pulse)), (c, c), end, 4)
        figure = (255, 248, 226, round(210 * pulse))
        head_y = c - 62
        pygame.draw.circle(glow, figure, (c, head_y), 26)
        pygame.draw.polygon(glow, figure, [(c - 30, head_y + 30), (c + 30, head_y + 30), (c + 68, c + 110), (c - 68, c + 110)])
        self.surface.blit(glow, glow.get_rect(center=(rect.centerx, rect.centery + 10)))

    def draw_cast(self, now):
        speaker = self.step["raw_who"] if self.step and self.step["command"] == "say" else None
        for member in self.cast:
            name = member["name"]
            speaking = name == speaker
            fade = min(1.0, (now - member["since"]) / FADE_MS)
            rect = pygame.Rect(0, 0, *PORTRAIT_SIZE)
            rect.midbottom = (round(SCREEN_WIDTH * SLOTS[member["slot"]]), PORTRAIT_BOTTOM - (14 if speaking else 0) + round(30 * (1 - fade)))
            if name in LIGHT_FIGURES:
                self.draw_light(rect, now, fade * (1.0 if speaking or speaker is None else 0.6))
                continue
            pygame.draw.rect(self.surface, (0, 0, 0), rect.move(8, 10), border_radius=12)
            image = self.portrait(name)
            if image:
                self.surface.blit(image, rect)
            else:
                pygame.draw.rect(self.surface, (40, 32, 24), rect, border_radius=10)
            dim = (0 if speaking or speaker is None else 110) + round(200 * (1 - fade))
            if dim:
                veil = pygame.Surface(rect.size, pygame.SRCALPHA)
                veil.fill((10, 8, 6, min(255, dim)))
                self.surface.blit(veil, rect)
            pygame.draw.rect(self.surface, GOLD if speaking else CARD_EDGE, rect, 4 if speaking else 2, border_radius=10)
            if not speaking:  # the speaker's name is on the text box
                label = get_font(24, bold=True).render(self.fill(name), True, DIM)
                self.surface.blit(label, label.get_rect(midtop=(rect.centerx, rect.bottom + 4)))

    def panel(self, rect):
        if self.frame:
            draw_nine_slice_panel(self.surface, rect, self.frame)
            return frame_content_rect(rect, self.frame)
        pygame.draw.rect(self.surface, (24, 18, 12), rect, border_radius=10)
        pygame.draw.rect(self.surface, GOLD, rect, 3, border_radius=10)
        return rect.inflate(-48, -40)

    def shade(self, alpha):
        veil = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        veil.fill((8, 6, 4, alpha))
        self.surface.blit(veil, (0, 0))

    def draw_text_box(self, now):
        step = self.step
        content = self.panel(TEXT_BOX)
        name_font, text_font = get_font(36, bold=True), get_font(32)
        top = content.y
        if step["command"] == "say":
            self.surface.blit(name_font.render(step["who"], True, GOLD), (content.x, top))
            top += name_font.get_linesize() + 4
        text = step["who"] if step["command"] == "choice" else step["text"]
        color = TEXT if step["command"] == "say" else NARRATION
        shown = len(text) if step["typed"] else int((now - step["start"]) * TYPE_SPEED / 1000)
        for line in wrap(text, text_font, content.width):
            if shown <= 0:
                break
            self.surface.blit(text_font.render(line[:shown], True, color), (content.x, top))
            shown -= len(line) + 1
            top += text_font.get_linesize()
        if step["typed"] and step["command"] != "choice":
            bob = round(4 * math.sin(now / 180))
            x, y = content.right - 18, content.bottom - 16 + bob
            pygame.draw.polygon(self.surface, GOLD, [(x - 12, y - 10), (x + 12, y - 10), (x, y + 4)])

    def draw_choices(self):
        font = get_font(30)
        for i, (rect, option) in enumerate(zip(self.choice_rects(), self.step["options"])):
            hovered = i == self.hover
            pygame.draw.rect(self.surface, BUTTON_HOVER if hovered else BUTTON, rect, border_radius=10)
            pygame.draw.rect(self.surface, GOLD if hovered else CARD_EDGE, rect, 3 if hovered else 2, border_radius=10)
            label = font.render(f"{i + 1}.  {option}", True, TEXT)
            self.surface.blit(label, label.get_rect(center=rect.center))

    def draw_title(self, now):
        fade = min(1.0, (now - self.step["start"]) / 700)
        self.shade(round(235 * min(1.0, fade * 1.5)))
        heading = get_font(30, bold=True).render(self.step["who"].upper(), True, GOLD)
        title = get_font(78, bold=True).render(self.step["text"], True, TEXT)
        for surf in (heading, title):
            surf.set_alpha(round(255 * fade))
        self.surface.blit(heading, heading.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 70)))
        self.surface.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 10)))
        pygame.draw.line(self.surface, GOLD, (SCREEN_WIDTH // 2 - 160, SCREEN_HEIGHT // 2 + 75), (SCREEN_WIDTH // 2 + 160, SCREEN_HEIGHT // 2 + 75), 2)
        self.draw_hint("Click / Enter to continue")

    def draw_scripture(self):
        self.shade(170)
        verse_font, ref_font = get_font(36), get_font(30, bold=True)
        lines = wrap(f"“{self.step['text']}”", verse_font, 1000)
        height = len(lines) * verse_font.get_linesize() + 200
        content = self.panel(pygame.Rect(SCREEN_WIDTH // 2 - 620, SCREEN_HEIGHT // 2 - height // 2 - 40, 1240, height))
        y = content.y + 10
        for line in lines:
            rendered = verse_font.render(line, True, TEXT)
            self.surface.blit(rendered, rendered.get_rect(midtop=(content.centerx, y)))
            y += verse_font.get_linesize()
        ref = ref_font.render(f"- {self.step['who']} (WEB)", True, GOLD)
        self.surface.blit(ref, ref.get_rect(topright=(content.right - 20, y + 14)))
        self.draw_hint("Click / Enter to continue")

    def draw_reflect(self):
        self.shade(200)
        head, sub, body = get_font(46, bold=True), get_font(26), get_font(30)
        content = self.panel(pygame.Rect(180, 90, SCREEN_WIDTH - 360, SCREEN_HEIGHT - 180))
        title = head.render(f"Read {self.step['who']}", True, GOLD)
        self.surface.blit(title, title.get_rect(midtop=(content.centerx, content.y)))
        note = sub.render("Talk it over - with a friend, your family or your youth group", True, DIM)
        self.surface.blit(note, note.get_rect(midtop=(content.centerx, content.y + 66)))
        y = content.y + 130
        for i, question in enumerate(q.strip() for q in self.step["text"].split("|") if q.strip()):
            lines = wrap(question, body, content.width - 120)
            self.surface.blit(body.render(f"{i + 1}.", True, GOLD), (content.x + 40, y))
            for line in lines:
                self.surface.blit(body.render(line, True, TEXT), (content.x + 90, y))
                y += body.get_linesize()
            y += 22
        self.draw_hint("Click / Enter to continue")

    def draw_hint(self, text):
        hint = get_font(24).render(text, True, DIM)
        self.surface.blit(hint, hint.get_rect(midbottom=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 18)))

    def draw_buttons(self):
        font = get_font(26, bold=True)
        mouse = pygame.mouse.get_pos()
        for rect, label in ((LOG_BUTTON, "Log"), (SKIP_BUTTON, "Skip >>")):
            hovered = rect.collidepoint(mouse)
            pygame.draw.rect(self.surface, BUTTON_HOVER if hovered else BUTTON, rect, border_radius=8)
            pygame.draw.rect(self.surface, GOLD if hovered else CARD_EDGE, rect, 2, border_radius=8)
            rendered = font.render(label, True, TEXT)
            self.surface.blit(rendered, rendered.get_rect(center=rect.center))

    def draw_log(self):
        self.shade(160)
        content = self.panel(LOG_PANEL)
        name_font, font = get_font(26, bold=True), get_font(28)
        lines = []
        for who, text in self.log:
            if who:
                lines.append((GOLD, name_font, who))
            lines.extend((TEXT if who else NARRATION, font, line) for line in wrap(text, font, content.width - 30))
            lines.append(None)
        per_page = max(1, (content.height - 50) // font.get_linesize())
        self.log_scroll = min(self.log_scroll, max(0, len(lines) - per_page))
        end = len(lines) - self.log_scroll
        y = content.y
        for entry in lines[max(0, end - per_page):end]:
            if entry:
                color, entry_font, line = entry
                self.surface.blit(entry_font.render(line, True, color), (content.x + 10, y))
            y += font.get_linesize() if entry else 10
        hint = get_font(22).render("Wheel / Up-Down to scroll  -  click or Esc to close", True, DIM)
        self.surface.blit(hint, hint.get_rect(bottomright=(content.right, content.bottom)))

    def draw(self):
        now = pygame.time.get_ticks()
        if self.backdrop:
            self.backdrop.draw(self.surface)
        else:
            self.surface.fill((14, 11, 8))
        command = self.step["command"]
        if command != "title":
            self.draw_cast(now)
        if command in ("say", "narrate", "choice"):
            self.draw_text_box(now)
        if command == "choice":
            self.draw_choices()
        elif command == "title":
            self.draw_title(now)
        elif command == "scripture":
            self.draw_scripture()
        elif command == "reflect":
            self.draw_reflect()
        if self.log_open:
            self.draw_log()
        else:
            self.draw_buttons()

    async def run(self):
        self.step = self.next_step()
        while self.step is not None:
            for event in pygame.event.get():
                self.handle(event)
                if self.step is None:
                    break
            if self.step is None:
                break
            self.typing()
            self.voice.update((self.step["who"], self.step["text"]) if self.step["command"] == "say" else None)
            self.draw()
            pygame.display.flip()
            self.clock.tick(60)
            await asyncio.sleep(0)
        self.voice.update(None)
        return self.choice


async def play_scene(surface, scene_id, hero_name=None, story=None):
    """Plays one scene; False if there's no such scene."""
    story = story if story is not None else load_story()
    rows = story.get(scene_id)
    if not rows:
        return False
    await StoryPlayer(surface, rows, hero_name=hero_name, seed=scene_id).run()
    return True

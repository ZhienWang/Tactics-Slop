"""The game's front door: a title screen, and for a New Game the survey that
decides the hero's class (see scripts/hero.py) - Paul, the hero's advisor,
introduces it, the player picks the super short (4), short (12) or long (30)
version - or skips it and picks a class outright - the questions follow, the player names their character,
and the result screen shows the class, its skills and Paul's counsel.

Every screen is its own small async loop (awaiting asyncio.sleep(0) each
frame, like the battle) so the browser build keeps running.
"""
import asyncio
import sys

import pygame

from scripts.assets import draw_nine_slice_panel, get_font, load_image_safe, load_nine_slice_frame
from scripts.config import SCREEN_HEIGHT, SCREEN_WIDTH
from scripts.game_logic import SIGNATURE_PREVIEW, run_first_stage
from scripts.hero import (
    DEFAULT_HERO_NAME, HERO_TOKEN, MAX_NAME_LENGTH, ROLE_COLORS, load_classes_from_csv, load_profile,
    load_survey_from_csv, save_profile, score_survey,
)
from scripts.skybox import Skybox

TEXT = (240, 232, 214)
DIM = (190, 180, 160)
GOLD = (255, 215, 110)
BUTTON = (58, 44, 32)
BUTTON_HOVER = (96, 72, 46)
PAUL_TOKEN = "assets/paul.png"
PAUL_INTRO = ("Before we set out together, friend, let me know you a little. Answer as you truly are, "
              "not as you wish you were - there are no wrong answers, and every kind of servant has a place in this work.")


def wrap(text, font, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if font.size(trial)[0] <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def blit_wrapped(surface, text, font, color, x, y, width, line_gap=6, center=False):
    for line in wrap(text, font, width):
        rendered = font.render(line, True, color)
        surface.blit(rendered, rendered.get_rect(midtop=(x + width // 2, y)) if center else (x, y))
        y += rendered.get_height() + line_gap
    return y


class Screen:
    """Shared frame drawing: the sky behind, a framed panel in front."""

    def __init__(self, surface):
        self.surface = surface
        self.sky = Skybox("sunny", SCREEN_WIDTH, SCREEN_HEIGHT, seed="title")
        self.frame = load_nine_slice_frame([])
        self.clock = pygame.time.Clock()

    def backdrop(self):
        self.sky.draw(self.surface, 2, 0, 0)
        shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        shade.fill((10, 8, 6, 90))
        self.surface.blit(shade, (0, 0))

    def panel(self, rect):
        if self.frame:
            draw_nine_slice_panel(self.surface, rect, self.frame)
        else:
            pygame.draw.rect(self.surface, (30, 24, 18), rect)
            pygame.draw.rect(self.surface, GOLD, rect, 3)

    def button(self, rect, label, hovered, font, color=TEXT):
        pygame.draw.rect(self.surface, BUTTON_HOVER if hovered else BUTTON, rect, border_radius=8)
        pygame.draw.rect(self.surface, GOLD if hovered else (150, 120, 80), rect, 2, border_radius=8)
        lines = wrap(label, font, rect.width - 40)
        total = sum(font.get_height() + 4 for _ in lines) - 4
        y = rect.centery - total // 2
        for line in lines:
            rendered = font.render(line, True, color)
            self.surface.blit(rendered, rendered.get_rect(midtop=(rect.centerx, y)))
            y += font.get_height() + 4

    def portrait(self, path, rect):
        image = load_image_safe(path)
        if image:
            scale = min(rect.width / image.get_width(), rect.height / image.get_height())
            image = pygame.transform.smoothscale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
            self.surface.blit(image, image.get_rect(center=rect.center))

    async def flip(self):
        pygame.display.flip()
        self.clock.tick(60)
        await asyncio.sleep(0)


def quit_game():
    pygame.quit()
    sys.exit()


async def title_screen(screen):
    """Returns "new" or "continue"."""
    has_save = load_profile() is not None
    options = [("new", "New Game")] + ([("continue", "Continue")] if has_save else [])
    index = 1 if has_save else 0
    title_font, sub_font, button_font = get_font(84, bold=True), get_font(28), get_font(34)
    while True:
        rects = [pygame.Rect(SCREEN_WIDTH // 2 - 180, 470 + i * 90, 360, 70) for i in range(len(options))]
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_game()
            if event.type == pygame.MOUSEMOTION:
                index = next((i for i, r in enumerate(rects) if r.collidepoint(event.pos)), index)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                hit = next((i for i, r in enumerate(rects) if r.collidepoint(event.pos)), None)
                if hit is not None:
                    return options[hit][0]
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    index = (index - 1) % len(options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    index = (index + 1) % len(options)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return options[index][0]
        screen.backdrop()
        title = title_font.render("The Road to Jerusalem", True, GOLD)
        screen.surface.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 250)))
        sub = sub_font.render("A tactics pilgrimage through the Acts of the Apostles", True, TEXT)
        screen.surface.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, 330)))
        for i, ((_, label), rect) in enumerate(zip(options, rects)):
            screen.button(rect, label, i == index, button_font)
        await screen.flip()


async def paul_intro(screen):
    """Paul, the advisor, introduces the survey."""
    font, name_font, hint_font = get_font(32), get_font(38, bold=True), get_font(24)
    panel = pygame.Rect(200, 220, SCREEN_WIDTH - 400, 420)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_game()
            if (event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE)) or \
                    (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1):
                return
        screen.backdrop()
        screen.panel(panel)
        screen.portrait(PAUL_TOKEN, pygame.Rect(panel.x + 40, panel.y + 60, 300, 150))
        screen.surface.blit(name_font.render("Paul - your advisor", True, GOLD), (panel.x + 370, panel.y + 60))
        blit_wrapped(screen.surface, PAUL_INTRO, font, TEXT, panel.x + 370, panel.y + 120, panel.width - 430)
        hint = hint_font.render("[Click / Enter] Begin", True, DIM)
        screen.surface.blit(hint, hint.get_rect(bottomright=(panel.right - 40, panel.bottom - 30)))
        await screen.flip()


async def length_screen(screen):
    """Which survey - super short, short or long - or skip it and pick a
    class outright? Returns "super_short", "short", "long" or "pick"."""
    count = {version: len(load_survey_from_csv(version=version)) for version in ("super_short", "short", "long")}
    options = [("super_short", f"Super Short - {count['super_short']} questions", "One question for each letter of your type."),
               ("short", f"Short - {count['short']} questions", "A quick read on who you are."),
               ("long", f"Long - {count['long']} questions", "Takes longer, but knows you better."),
               ("pick", "Choose my class", "Skip the questions - pick from all sixteen.")]
    head, body, small = get_font(40, bold=True), get_font(34, bold=True), get_font(26)
    panel = pygame.Rect(300, 70, SCREEN_WIDTH - 600, 760)
    index = 0
    while True:
        rects = [pygame.Rect(panel.x + 80, panel.y + 130 + i * 140, panel.width - 160, 115) for i in range(len(options))]
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_game()
            if event.type == pygame.MOUSEMOTION:
                index = next((i for i, r in enumerate(rects) if r.collidepoint(event.pos)), index)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                hit = next((i for i, r in enumerate(rects) if r.collidepoint(event.pos)), None)
                if hit is not None:
                    return options[hit][0]
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    index = (index - 1) % len(options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    index = (index + 1) % len(options)
                elif event.key in NUMBER_KEYS and NUMBER_KEYS[event.key] < len(options):
                    return options[NUMBER_KEYS[event.key]][0]
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return options[index][0]
        screen.backdrop()
        screen.panel(panel)
        prompt = head.render("How long shall we talk?", True, GOLD)
        screen.surface.blit(prompt, prompt.get_rect(midtop=(panel.centerx, panel.y + 60)))
        for i, (rect, (_, label, detail)) in enumerate(zip(rects, options)):
            screen.button(rect, "", i == index, body)
            title = body.render(f"{i + 1}.  {label}", True, TEXT)
            screen.surface.blit(title, title.get_rect(midtop=(rect.centerx, rect.y + 20)))
            sub = small.render(detail, True, DIM)
            screen.surface.blit(sub, sub.get_rect(midtop=(rect.centerx, rect.y + 68)))
        await screen.flip()


NUMBER_KEYS = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3,
               pygame.K_KP1: 0, pygame.K_KP2: 1, pygame.K_KP3: 2, pygame.K_KP4: 3}
ROLES = ("Analyst", "Diplomat", "Sentinel", "Explorer")


async def class_picker(screen, classes, current=None):
    """All sixteen classes in a grid - a column per role. Returns the
    chosen type code, or None if the player backs out (Esc / Back)."""
    columns = [[c for c in classes.values() if c["role"] == role] for role in ROLES]
    head, name_font, small = get_font(40, bold=True), get_font(30, bold=True), get_font(22)
    panel = pygame.Rect(60, 40, SCREEN_WIDTH - 120, SCREEN_HEIGHT - 80)
    card_w, card_h = (panel.width - 160) // 4, 118
    col, row = 0, 0
    for c, column in enumerate(columns):
        for r, cls in enumerate(column):
            if cls["type"] == current:
                col, row = c, r
    back_rect = pygame.Rect(panel.x + 60, panel.bottom - 85, 160, 50)
    while True:
        cards = {(c, r): pygame.Rect(panel.x + 60 + c * (card_w + 13), panel.y + 150 + r * (card_h + 12), card_w, card_h)
                 for c in range(4) for r in range(len(columns[c]))}
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_game()
            if event.type == pygame.MOUSEMOTION:
                col, row = next((key for key, rect in cards.items() if rect.collidepoint(event.pos)), (col, row))
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                hit = next((key for key, rect in cards.items() if rect.collidepoint(event.pos)), None)
                if hit:
                    return columns[hit[0]][hit[1]]["type"]
                if back_rect.collidepoint(event.pos):
                    return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    col = (col - 1) % 4
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    col = (col + 1) % 4
                elif event.key in (pygame.K_UP, pygame.K_w):
                    row = (row - 1) % len(columns[col])
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    row = (row + 1) % len(columns[col])
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return columns[col][row]["type"]
                row = min(row, len(columns[col]) - 1)
        screen.backdrop()
        screen.panel(panel)
        prompt = head.render("Choose your class", True, GOLD)
        screen.surface.blit(prompt, prompt.get_rect(midtop=(panel.centerx, panel.y + 45)))
        for c, role in enumerate(ROLES):
            label = name_font.render(f"{role}s", True, ROLE_COLORS[role])
            screen.surface.blit(label, label.get_rect(midtop=(panel.x + 60 + c * (card_w + 13) + card_w // 2, panel.y + 105)))
        for (c, r), rect in cards.items():
            cls = columns[c][r]
            selected = (c, r) == (col, row)
            pygame.draw.rect(screen.surface, BUTTON_HOVER if selected else BUTTON, rect, border_radius=8)
            pygame.draw.rect(screen.surface, ROLE_COLORS[cls["role"]] if selected else (120, 96, 66), rect, 3 if selected else 1, border_radius=8)
            screen.surface.blit(name_font.render(cls["class"], True, ROLE_COLORS[cls["role"]]), (rect.x + 16, rect.y + 12))
            screen.surface.blit(small.render(cls["type"], True, GOLD), (rect.x + 16, rect.y + 52))
            screen.surface.blit(small.render(f"Signature: {cls['signature']}", True, TEXT), (rect.x + 16, rect.y + 82))
        chosen = columns[col][row]
        blit_wrapped(screen.surface, f"{chosen['class']} - {chosen['blurb']}", small, TEXT,
                     back_rect.right + 40, back_rect.y - 6, panel.right - back_rect.right - 100)
        screen.button(back_rect, "Back", back_rect.collidepoint(pygame.mouse.get_pos()), small)
        await screen.flip()


async def survey_screen(screen, questions):
    """Returns the chosen answer index (0/1) for each question. Backspace
    (or the Back button) returns to the previous question."""
    answers = []
    question_font, answer_font, small_font = get_font(38, bold=True), get_font(30), get_font(24)
    panel = pygame.Rect(160, 110, SCREEN_WIDTH - 320, SCREEN_HEIGHT - 220)
    hovered = None
    while len(answers) < len(questions):
        question = questions[len(answers)]
        choice_rects = [pygame.Rect(panel.x + 70, panel.y + 300 + i * 130, panel.width - 140, 105) for i in range(2)]
        back_rect = pygame.Rect(panel.x + 70, panel.bottom - 90, 160, 50)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_game()
            if event.type == pygame.MOUSEMOTION:
                hovered = next((i for i, r in enumerate(choice_rects) if r.collidepoint(event.pos)), None)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                hit = next((i for i, r in enumerate(choice_rects) if r.collidepoint(event.pos)), None)
                if hit is not None:
                    answers.append(hit)
                elif back_rect.collidepoint(event.pos) and answers:
                    answers.pop()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_1, pygame.K_a, pygame.K_LEFT, pygame.K_KP1):
                    answers.append(0)
                elif event.key in (pygame.K_2, pygame.K_b, pygame.K_RIGHT, pygame.K_KP2):
                    answers.append(1)
                elif event.key == pygame.K_BACKSPACE and answers:
                    answers.pop()
            if len(answers) == len(questions):
                break
        if len(answers) == len(questions):
            break
        question = questions[len(answers)]
        screen.backdrop()
        screen.panel(panel)
        count = small_font.render(f"Question {len(answers) + 1} of {len(questions)}", True, DIM)
        screen.surface.blit(count, (panel.x + 70, panel.y + 55))
        bar = pygame.Rect(panel.x + 70, panel.y + 95, panel.width - 140, 10)
        pygame.draw.rect(screen.surface, (60, 48, 36), bar, border_radius=5)
        pygame.draw.rect(screen.surface, GOLD, (bar.x, bar.y, round(bar.width * len(answers) / len(questions)), bar.height), border_radius=5)
        blit_wrapped(screen.surface, question["question"], question_font, TEXT, panel.x + 70, panel.y + 150, panel.width - 140)
        for i, (rect, (label, _)) in enumerate(zip(choice_rects, question["answers"])):
            screen.button(rect, f"{i + 1}.  {label}", hovered == i, answer_font)
        if answers:
            screen.button(back_rect, "Back", back_rect.collidepoint(pygame.mouse.get_pos()), small_font)
        hint = small_font.render("Click an answer, or press 1 / 2", True, DIM)
        screen.surface.blit(hint, hint.get_rect(bottomright=(panel.right - 70, panel.bottom - 105)))
        await screen.flip()
    return answers


def browser_prompt(question, default):
    """The browser's own text prompt - how a phone (which never shows its
    keyboard for the game canvas) types a name. None outside the browser or
    if the player cancels."""
    if sys.platform != "emscripten":
        return None
    try:
        import platform
        answer = platform.window.prompt(question, default)
    except Exception:
        return None
    return None if answer is None or str(answer) in ("null", "undefined") else str(answer)


async def name_screen(screen):
    """Returns the hero's name (the default if left blank). Tapping the name
    box in the browser opens the device's text prompt; OK confirms."""
    name = ""
    prompt_font, input_font, hint_font = get_font(40, bold=True), get_font(44), get_font(24)
    panel = pygame.Rect(350, 250, SCREEN_WIDTH - 700, 420)
    box = pygame.Rect(panel.x + 90, panel.y + 150, panel.width - 180, 80)
    ok_rect = pygame.Rect(panel.centerx - 110, panel.y + 300, 220, 64)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_game()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if ok_rect.collidepoint(event.pos):
                    return name.strip() or DEFAULT_HERO_NAME
                if box.collidepoint(event.pos):
                    typed = browser_prompt("What is your name?", name or DEFAULT_HERO_NAME)
                    if typed is not None:
                        name = typed.strip()[:MAX_NAME_LENGTH]
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return name.strip() or DEFAULT_HERO_NAME
                if event.key == pygame.K_BACKSPACE:
                    name = name[:-1]
                elif event.unicode and event.unicode.isprintable() and len(name) < MAX_NAME_LENGTH:
                    name += event.unicode
        screen.backdrop()
        screen.panel(panel)
        prompt = prompt_font.render("And what is your name?", True, GOLD)
        screen.surface.blit(prompt, prompt.get_rect(midtop=(panel.centerx, panel.y + 60)))
        pygame.draw.rect(screen.surface, (24, 18, 12), box, border_radius=8)
        pygame.draw.rect(screen.surface, GOLD, box, 2, border_radius=8)
        shown = name or DEFAULT_HERO_NAME
        caret = "|" if name and (pygame.time.get_ticks() // 500) % 2 else ""
        text = input_font.render(shown + caret, True, TEXT if name else (120, 110, 95))
        screen.surface.blit(text, text.get_rect(midleft=(box.x + 24, box.centery)))
        hint = hint_font.render("Type a name (or tap the box) and press Enter / OK", True, DIM)
        screen.surface.blit(hint, hint.get_rect(midtop=(panel.centerx, box.bottom + 18)))
        screen.button(ok_rect, "OK", ok_rect.collidepoint(pygame.mouse.get_pos()), prompt_font)
        await screen.flip()


async def result_screen(screen, profile, cls):
    """The class reveal and Paul's counsel. Returns "begin", "retake" or
    "choose" (pick a different class by hand)."""
    big, head, body, small = get_font(64, bold=True), get_font(34, bold=True), get_font(28), get_font(24)
    role_color = ROLE_COLORS[cls["role"]]
    panel = pygame.Rect(90, 50, SCREEN_WIDTH - 180, SCREEN_HEIGHT - 100)
    begin_rect = pygame.Rect(panel.right - 330, panel.bottom - 100, 260, 60)
    retake_rect = pygame.Rect(panel.right - 610, panel.bottom - 100, 260, 60)
    choose_rect = pygame.Rect(panel.right - 890, panel.bottom - 100, 260, 60)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_game()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if begin_rect.collidepoint(event.pos):
                    return "begin"
                if retake_rect.collidepoint(event.pos):
                    return "retake"
                if choose_rect.collidepoint(event.pos):
                    return "choose"
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                return "begin"
        screen.backdrop()
        screen.panel(panel)
        left = panel.x + 70
        screen.surface.blit(small.render(f"{profile['name']}, you are", True, DIM), (left, panel.y + 55))
        title = big.render(f"The {cls['class']}", True, role_color)
        screen.surface.blit(title, (left, panel.y + 85))
        code = head.render(f"{cls['type']}  -  {cls['role']}", True, GOLD)
        screen.surface.blit(code, (left, panel.y + 165))
        y = blit_wrapped(screen.surface, cls["blurb"], body, TEXT, left, panel.y + 225, 820)
        y += 20
        screen.surface.blit(head.render("Skills", True, GOLD), (left, y))
        y += 50
        for skill in cls["skills"]:
            signature = skill == cls["signature"]
            label = f"{skill}  (signature)" if signature else skill
            screen.surface.blit(body.render(label, True, role_color if signature else TEXT), (left + 20, y))
            if signature:
                detail = SIGNATURE_PREVIEW.get(skill, "Ranged disarm, 4 tiles" if skill == "Sling" else "")
                screen.surface.blit(small.render(detail, True, DIM), (left + 420, y + 4))
            y += 40
        screen.portrait(HERO_TOKEN.format(role=cls["role"].lower()), pygame.Rect(panel.right - 470, panel.y + 60, 400, 200))
        counsel = pygame.Rect(panel.right - 560, panel.y + 290, 490, 330)
        pygame.draw.rect(screen.surface, (28, 22, 16), counsel, border_radius=10)
        pygame.draw.rect(screen.surface, (150, 120, 80), counsel, 2, border_radius=10)
        screen.portrait(PAUL_TOKEN, pygame.Rect(counsel.x + 10, counsel.y + 10, 160, 80))
        screen.surface.blit(head.render("Paul's counsel", True, GOLD), (counsel.x + 180, counsel.y + 30))
        blit_wrapped(screen.surface, f"“{cls['advice']}”", small, TEXT, counsel.x + 30, counsel.y + 110, counsel.width - 60)
        screen.button(choose_rect, "Choose class", choose_rect.collidepoint(pygame.mouse.get_pos()), small)
        screen.button(retake_rect, "Retake survey", retake_rect.collidepoint(pygame.mouse.get_pos()), small)
        screen.button(begin_rect, "Set out", begin_rect.collidepoint(pygame.mouse.get_pos()), head)
        await screen.flip()


async def new_game(screen):
    """Survey (super short, short or long) or a class picked outright -> name -> result,
    until the player sets out; the result screen can retake the survey or
    swap in a hand-picked class. Returns the saved profile."""
    classes = load_classes_from_csv()
    await paul_intro(screen)
    mode = await length_screen(screen)
    name, hero_type = None, None
    while True:
        if hero_type is None:
            if mode == "pick":
                hero_type = await class_picker(screen, classes)
                if hero_type is None:  # backed out - ask again
                    mode = await length_screen(screen)
                    continue
            else:
                questions = load_survey_from_csv(version=mode)
                hero_type = score_survey(questions, await survey_screen(screen, questions))
        if name is None:
            name = await name_screen(screen)
        profile = {"name": name, "type": hero_type}
        action = await result_screen(screen, profile, classes[hero_type])
        if action == "begin":
            save_profile(profile)
            return profile
        if action == "retake":
            hero_type = None
            mode = await length_screen(screen)
        elif action == "choose":
            hero_type = await class_picker(screen, classes, current=hero_type) or hero_type


async def start_game():
    """Title screen, then (for a new game) the survey, then the first battle."""
    pygame.init()
    surface = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("The Road to Jerusalem")
    screen = Screen(surface)
    choice = await title_screen(screen)
    profile = load_profile() if choice == "continue" else None
    if profile is None:
        profile = await new_game(screen)
    return await run_first_stage(hero=profile)

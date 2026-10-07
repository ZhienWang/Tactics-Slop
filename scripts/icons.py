"""Icons for the action menu - drawn in code as simple flat glyphs, so the
menu needs no image files and every new skill or item gets an icon (its own
glyph, or its skill type's) without any art work.

Each icon is drawn at SUPERSAMPLE times its size on a coloured tile and
scaled down for smooth edges, then cached. Glyphs are laid out in a 100x100
box (see the `g_*` functions), so they scale to any tile size.
"""
import math

import pygame

SUPERSAMPLE = 3
GLYPH = (250, 244, 228)
GLYPH_DARK = (60, 44, 30)
SIGNATURE_STAR = (255, 210, 80)

# Tile colours, by what the tile is.
COMMAND_COLOR = (120, 86, 46)
WAIT_COLOR = (82, 82, 92)
BACK_COLOR = (120, 52, 46)
ITEM_COLOR = (46, 112, 112)
SKILL_TYPE_COLORS = {
    "Faith": (176, 132, 36),
    "Physical": (156, 52, 44),
    "Heal": (54, 132, 70),
    "Support": (52, 96, 160),
    "Status": (112, 64, 140),
}

_cache = {}


# --- glyphs (drawn into a 100x100 box scaled by k) -------------------------------

def _p(points, k):
    return [(x * k, y * k) for x, y in points]


def g_footprints(s, k, c):
    for ox, oy, flip in ((22, 40, 1), (54, 14, -1)):
        pygame.draw.ellipse(s, c, pygame.Rect((ox) * k, (oy + 14) * k, 22 * k, 34 * k))
        pygame.draw.ellipse(s, c, pygame.Rect((ox + 2) * k, (oy + 50) * k, 18 * k, 14 * k))
    for ox, oy in ((22, 40), (54, 14)):
        for i, (dx, dy) in enumerate(((2, 6), (9, 2), (16, 4))):
            pygame.draw.circle(s, c, ((ox + dx + 2) * k, (oy + dy) * k), 3.6 * k)


def g_sparkle(s, k, c):
    pygame.draw.polygon(s, c, _p([(50, 8), (60, 40), (92, 50), (60, 60), (50, 92), (40, 60), (8, 50), (40, 40)], k))
    pygame.draw.polygon(s, c, _p([(80, 10), (84, 20), (94, 24), (84, 28), (80, 38), (76, 28), (66, 24), (76, 20)], k))


def g_pouch(s, k, c):
    pygame.draw.ellipse(s, c, pygame.Rect(18 * k, 34 * k, 64 * k, 58 * k))
    pygame.draw.polygon(s, c, _p([(36, 36), (64, 36), (72, 18), (28, 18)], k))
    pygame.draw.line(s, GLYPH_DARK, (30 * k, 34 * k), (70 * k, 34 * k), int(5 * k))


def g_hourglass(s, k, c):
    pygame.draw.rect(s, c, pygame.Rect(22 * k, 10 * k, 56 * k, 8 * k))
    pygame.draw.rect(s, c, pygame.Rect(22 * k, 82 * k, 56 * k, 8 * k))
    pygame.draw.polygon(s, c, _p([(28, 18), (72, 18), (54, 50), (72, 82), (28, 82), (46, 50)], k))
    pygame.draw.polygon(s, GLYPH_DARK, _p([(36, 24), (64, 24), (50, 44)], k))


def g_back(s, k, c):
    pygame.draw.arc(s, c, pygame.Rect(26 * k, 22 * k, 56 * k, 56 * k), -math.pi / 2, math.pi / 2, int(11 * k))
    pygame.draw.polygon(s, c, _p([(8, 26), (38, 6), (38, 46)], k))
    pygame.draw.rect(s, c, pygame.Rect(34 * k, 21 * k, 22 * k, 11 * k))
    pygame.draw.rect(s, c, pygame.Rect(26 * k, 68 * k, 30 * k, 11 * k))


def g_book(s, k, c):
    pygame.draw.polygon(s, c, _p([(8, 24), (46, 30), (46, 86), (8, 78)], k))
    pygame.draw.polygon(s, c, _p([(92, 24), (54, 30), (54, 86), (92, 78)], k))
    for y in (42, 54, 66):
        pygame.draw.line(s, GLYPH_DARK, (16 * k, (y - 2) * k), (40 * k, (y + 2) * k), int(3 * k))
        pygame.draw.line(s, GLYPH_DARK, (60 * k, (y + 2) * k), (84 * k, (y - 2) * k), int(3 * k))


def g_chain(s, k, c):
    for cx, cy in ((32, 36), (68, 64)):
        rect = pygame.Rect((cx - 22) * k, (cy - 14) * k, 44 * k, 28 * k)
        pygame.draw.ellipse(s, c, rect, int(9 * k))
    pygame.draw.line(s, c, (44 * k, 44 * k), (56 * k, 56 * k), int(10 * k))


def g_plus(s, k, c, ring=False):
    if ring:
        pygame.draw.circle(s, c, (50 * k, 50 * k), 42 * k, int(6 * k))
    pygame.draw.rect(s, c, pygame.Rect(40 * k, 18 * k, 20 * k, 64 * k))
    pygame.draw.rect(s, c, pygame.Rect(18 * k, 40 * k, 64 * k, 20 * k))


def g_flag(s, k, c):
    pygame.draw.rect(s, c, pygame.Rect(18 * k, 10 * k, 8 * k, 82 * k))
    pygame.draw.polygon(s, c, _p([(26, 12), (86, 26), (26, 52)], k))


def g_shield(s, k, c, cross=False):
    pygame.draw.polygon(s, c, _p([(50, 8), (88, 20), (82, 60), (50, 92), (18, 60), (12, 20)], k))
    if cross:
        pygame.draw.rect(s, GLYPH_DARK, pygame.Rect(45 * k, 22 * k, 10 * k, 56 * k))
        pygame.draw.rect(s, GLYPH_DARK, pygame.Rect(30 * k, 38 * k, 40 * k, 10 * k))


def g_sword(s, k, c):
    pygame.draw.polygon(s, c, _p([(84, 8), (92, 16), (40, 68), (32, 60)], k))
    pygame.draw.line(s, c, (20 * k, 56 * k), (44 * k, 80 * k), int(9 * k))
    pygame.draw.line(s, c, (32 * k, 68 * k), (14 * k, 86 * k), int(10 * k))


def g_bow(s, k, c):
    pygame.draw.arc(s, c, pygame.Rect(14 * k, 10 * k, 60 * k, 80 * k), -math.pi / 2, math.pi / 2, int(8 * k))
    pygame.draw.line(s, c, (44 * k, 12 * k), (44 * k, 88 * k), int(3 * k))
    pygame.draw.line(s, c, (30 * k, 50 * k), (90 * k, 50 * k), int(5 * k))
    pygame.draw.polygon(s, c, _p([(96, 50), (82, 40), (82, 60)], k))


def g_sling(s, k, c):
    pygame.draw.arc(s, c, pygame.Rect(10 * k, 14 * k, 70 * k, 70 * k), math.pi * 0.6, math.pi * 1.6, int(6 * k))
    pygame.draw.circle(s, c, (70 * k, 30 * k), 15 * k)


def g_horn(s, k, c):
    pygame.draw.polygon(s, c, _p([(14, 40), (40, 40), (82, 14), (82, 86), (40, 60), (14, 60)], k))
    for i in range(3):
        pygame.draw.arc(s, c, pygame.Rect((76 + i * 4) * k, (30 - i * 6) * k, 20 * k, (40 + i * 12) * k), -0.9, 0.9, int(3 * k))


def g_net(s, k, c):
    pygame.draw.circle(s, c, (50 * k, 50 * k), 40 * k, int(6 * k))
    for t in (30, 50, 70):
        pygame.draw.line(s, c, (t * k, 14 * k), (t * k, 86 * k), int(4 * k))
        pygame.draw.line(s, c, (14 * k, t * k), (86 * k, t * k), int(4 * k))


def g_shove(s, k, c):
    pygame.draw.rect(s, c, pygame.Rect(14 * k, 40 * k, 46 * k, 20 * k))
    pygame.draw.polygon(s, c, _p([(56, 22), (90, 50), (56, 78)], k))
    for y in (24, 50, 76):
        pygame.draw.line(s, c, (4 * k, y * k), (10 * k, y * k), int(5 * k))


def g_chevrons(s, k, c):
    for y in (20, 46):
        pygame.draw.polygon(s, c, _p([(50, y), (84, y + 30), (70, y + 30), (50, y + 14), (30, y + 30), (16, y + 30)], k))
    pygame.draw.rect(s, c, pygame.Rect(42 * k, 76 * k, 16 * k, 14 * k))


def g_spiral(s, k, c):
    points = []
    for i in range(120):
        t = i / 119 * 4.2 * math.pi
        r = 4 + t * 3.1
        points.append(((50 + r * math.cos(t)) * k, (50 + r * math.sin(t)) * k))
    pygame.draw.lines(s, c, False, points, int(7 * k))


def g_sun(s, k, c):
    pygame.draw.circle(s, c, (50 * k, 50 * k), 20 * k)
    for i in range(8):
        a = i * math.pi / 4
        pygame.draw.line(s, c, ((50 + 28 * math.cos(a)) * k, (50 + 28 * math.sin(a)) * k),
                         ((50 + 44 * math.cos(a)) * k, (50 + 44 * math.sin(a)) * k), int(7 * k))


def g_note(s, k, c):
    pygame.draw.ellipse(s, c, pygame.Rect(14 * k, 62 * k, 30 * k, 22 * k))
    pygame.draw.ellipse(s, c, pygame.Rect(56 * k, 54 * k, 30 * k, 22 * k))
    pygame.draw.rect(s, c, pygame.Rect(38 * k, 16 * k, 8 * k, 58 * k))
    pygame.draw.rect(s, c, pygame.Rect(80 * k, 8 * k, 8 * k, 58 * k))
    pygame.draw.polygon(s, c, _p([(38, 16), (88, 8), (88, 24), (38, 32)], k))


def g_bread(s, k, c):
    pygame.draw.ellipse(s, c, pygame.Rect(10 * k, 30 * k, 80 * k, 50 * k))
    for x in (34, 50, 66):
        pygame.draw.line(s, GLYPH_DARK, ((x - 6) * k, 42 * k), ((x + 6) * k, 58 * k), int(4 * k))


def g_scroll(s, k, c):
    pygame.draw.rect(s, c, pygame.Rect(22 * k, 18 * k, 56 * k, 64 * k))
    pygame.draw.circle(s, c, (22 * k, 24 * k), 10 * k)
    pygame.draw.circle(s, c, (78 * k, 76 * k), 10 * k)
    for y in (34, 46, 58):
        pygame.draw.line(s, GLYPH_DARK, (32 * k, y * k), (68 * k, y * k), int(3 * k))


def g_bubble(s, k, c):
    pygame.draw.ellipse(s, c, pygame.Rect(8 * k, 12 * k, 84 * k, 60 * k))
    pygame.draw.polygon(s, c, _p([(26, 62), (44, 66), (20, 90)], k))
    for x in (32, 50, 68):
        pygame.draw.circle(s, GLYPH_DARK, (x * k, 42 * k), 5 * k)


def g_die(s, k, c):
    pygame.draw.rect(s, c, pygame.Rect(14 * k, 14 * k, 72 * k, 72 * k), border_radius=int(12 * k))
    for x, y in ((32, 32), (68, 68), (50, 50), (68, 32), (32, 68)):
        pygame.draw.circle(s, GLYPH_DARK, (x * k, y * k), 7 * k)


def g_jar(s, k, c):
    pygame.draw.rect(s, c, pygame.Rect(30 * k, 10 * k, 40 * k, 12 * k))
    pygame.draw.rect(s, c, pygame.Rect(18 * k, 26 * k, 64 * k, 64 * k), border_radius=int(14 * k))
    pygame.draw.line(s, GLYPH_DARK, (30 * k, 52 * k), (70 * k, 52 * k), int(5 * k))


def g_ankh(s, k, c):
    pygame.draw.ellipse(s, c, pygame.Rect(32 * k, 6 * k, 36 * k, 38 * k), int(9 * k))
    pygame.draw.rect(s, c, pygame.Rect(45 * k, 40 * k, 10 * k, 52 * k))
    pygame.draw.rect(s, c, pygame.Rect(20 * k, 44 * k, 60 * k, 10 * k))


def g_vial(s, k, c):
    pygame.draw.rect(s, c, pygame.Rect(40 * k, 8 * k, 20 * k, 14 * k))
    pygame.draw.rect(s, c, pygame.Rect(43 * k, 22 * k, 14 * k, 18 * k))
    pygame.draw.circle(s, c, (50 * k, 64 * k), 28 * k)


def g_incense(s, k, c):
    pygame.draw.polygon(s, c, _p([(14, 66), (86, 66), (72, 90), (28, 90)], k))
    for x in (36, 52, 66):
        pygame.draw.arc(s, c, pygame.Rect((x - 8) * k, 10 * k, 16 * k, 26 * k), math.pi / 2, math.pi * 1.5, int(4 * k))
        pygame.draw.arc(s, c, pygame.Rect((x - 8) * k, 34 * k, 16 * k, 26 * k), -math.pi / 2, math.pi / 2, int(4 * k))


def g_seed(s, k, c):
    pygame.draw.ellipse(s, c, pygame.Rect(30 * k, 54 * k, 40 * k, 34 * k))
    pygame.draw.line(s, c, (50 * k, 56 * k), (50 * k, 24 * k), int(6 * k))
    pygame.draw.ellipse(s, c, pygame.Rect(50 * k, 12 * k, 32 * k, 18 * k))
    pygame.draw.ellipse(s, c, pygame.Rect(18 * k, 22 * k, 32 * k, 18 * k))


def g_eye(s, k, c, slash=False):
    pygame.draw.ellipse(s, c, pygame.Rect(8 * k, 28 * k, 84 * k, 44 * k))
    pygame.draw.circle(s, GLYPH_DARK, (50 * k, 50 * k), 15 * k)
    pygame.draw.circle(s, c, (55 * k, 45 * k), 5 * k)
    if slash:
        pygame.draw.line(s, GLYPH_DARK, (14 * k, 14 * k), (86 * k, 86 * k), int(13 * k))
        pygame.draw.line(s, c, (14 * k, 14 * k), (86 * k, 86 * k), int(7 * k))
    else:
        for x, y in ((50, 12), (24, 18), (76, 18)):
            pygame.draw.line(s, c, (x * k, y * k), ((50 + (x - 50) * 0.75) * k, (y + 8) * k), int(5 * k))


GLYPHS = {
    # commands
    "Move": g_footprints, "Act": g_sparkle, "Item": g_pouch, "Wait": g_hourglass, "Back": g_back,
    # skills
    "Preach": g_book, "Persecute": g_chain, "Arrest": g_chain, "Heal": g_plus,
    "First Aid": lambda s, k, c: g_plus(s, k, c, ring=True), "Lead": g_flag, "Marshal": g_flag,
    "Defend": g_shield, "Shield of Faith": lambda s, k, c: g_shield(s, k, c, cross=True),
    "Slash": g_sword, "Shoot": g_bow, "Sling": g_sling, "Command": g_horn, "Fish net": g_net,
    "Blind": lambda s, k, c: g_eye(s, k, c, slash=True), "Heal Blind": g_eye,
    "Shove": g_shove, "Rally": g_chevrons, "Inspire": g_sun, "Psalm": g_note, "Breaking Bread": g_bread,
    "Parable": g_scroll, "Good News": g_bubble, "Reason Together": g_bubble, "Bold Venture": g_die,
    "Disputation": g_spiral, "Grand Design": g_scroll, "Intercession": lambda s, k, c: g_plus(s, k, c, ring=True),
    "Peacemaker": g_shield, "Provision": g_pouch,
    # items
    "Healing Salve": g_jar, "Ankh": g_ankh, "Myrrh": g_vial, "Frankincense": g_incense, "Mustard Seed": g_seed,
}
TYPE_GLYPHS = {"Faith": g_book, "Physical": g_sword, "Heal": g_plus, "Support": g_chevrons, "Status": g_spiral}


def _star(surface, cx, cy, r, color):
    points = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else r * 0.45
        points.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    pygame.draw.polygon(surface, color, points)


def icon(name, size, tile_color, kind=None, signature=False, disabled=False):
    """A size x size icon tile for `name` (a command, skill or item). `kind`
    is the skill type, used for a skill without its own glyph."""
    key = (name, size, tile_color, kind, signature, disabled)
    if key in _cache:
        return _cache[key]
    big = size * SUPERSAMPLE
    surface = pygame.Surface((big, big), pygame.SRCALPHA)
    color = tuple(int(c * 0.45) for c in tile_color) if disabled else tile_color
    pygame.draw.rect(surface, color, surface.get_rect(), border_radius=big // 6)
    rim = tuple(min(255, int(c * 1.35) + 20) for c in color)
    pygame.draw.rect(surface, rim, surface.get_rect(), max(2, big // 32), border_radius=big // 6)
    glyph = GLYPHS.get(name) or TYPE_GLYPHS.get(kind) or g_sparkle
    inner = pygame.Surface((big, big), pygame.SRCALPHA)
    k = big * 0.62 / 100
    glyph(inner, k, (150, 150, 150) if disabled else GLYPH)
    offset = big * 0.19
    surface.blit(inner, (offset, offset))
    if signature:
        _star(surface, big * 0.8, big * 0.2, big * 0.15, SIGNATURE_STAR)
    result = pygame.transform.smoothscale(surface, (size, size))
    _cache[key] = result
    return result

import os
import sys
import math
import random
import asyncio
import pygame

from scripts.config import SCREEN_WIDTH, SCREEN_HEIGHT, CURSOR_COLOR, FAITH_CAP
from scripts.data_editor import (
    WORLD_MAP_CELL,
    world_grid_to_screen,
    load_world_map_rooms,
    load_items_from_csv,
    generate_dummy_csv_files,
    load_characters_from_csv,
    load_stage_manifest,
    load_world_map_nodes,
    load_equipment_from_csv,
    equipment_by_slot,
    UNIT_EQUIPMENT_SLOTS,
    load_books_from_csv,
    reading_level,
    BOOK_SLOTS,
)
from scripts.assets import build_character_face_portraits, load_image_safe, bring_window_to_front, load_nine_slice_frame, draw_nine_slice_panel, frame_content_rect, get_font
from scripts.game_logic import FIRST_STAGE_NODE, Unit, apply_book_growth, draw_stamina_dots, gain_exp, main as run_battle
from scripts import icons
from scripts.hero import load_classes_from_csv, save_profile
from scripts.hero_look import hero_token
from scripts.story import load_chapters, load_story, play_scene, scene_ids
from scripts.voices import MUSIC_VOLUME
from scripts.roster import LEADER, load_roster, recruited_after, recruits_for

# --- WORLD MAP DATA ---
# A grid of square spaces in the style of Super Mario Bros. 3's world maps:
# story and battle squares along straight roads, with library and party
# rooms off to the side (like Toad Houses). The layout lives in
# data/world_map_nodes.csv (col, row, type, connections) and the rooms'
# rewards in data/world_map_rooms.csv; this short route is the fallback if
# the file is missing or malformed.
_FALLBACK_NODES = {
    "damascus":  {"grid": (1, 1), "name": "Road to Damascus", "type": "stage", "connections": ["jerusalem"]},
    "jerusalem": {"grid": (4, 1), "name": "Jerusalem", "type": "stage", "connections": ["damascus", "caesarea"]},
    "caesarea":  {"grid": (4, 3), "name": "Caesarea", "type": "town", "connections": ["jerusalem", "antioch"]},
    "antioch":   {"grid": (7, 3), "name": "Antioch", "type": "stage", "connections": ["caesarea"]},
}
for _node in _FALLBACK_NODES.values():
    _node["pos"] = world_grid_to_screen(*_node["grid"], 9, 5)
try:
    NODES, START_NODE = load_world_map_nodes()
    if not NODES:
        raise ValueError("world_map_nodes.csv produced no nodes")
except (OSError, ValueError, KeyError):
    NODES, START_NODE = _FALLBACK_NODES, "damascus"
# Half the width of a square space, for clicks.
NODE_HALF = WORLD_MAP_CELL * 0.42

WORLD_THEME_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "world_theme.ogg")

STATE_MAP = "MAP"
STATE_TRANSITION = "TRANSITION"
STATE_MENU = "MENU"
STATE_UNIT_LIST = "UNIT_LIST"
STATE_UNIT_DETAIL = "UNIT_DETAIL"
STATE_EQUIPMENT = "EQUIPMENT"
STATE_BOOKS = "BOOKS"
STATE_STORY = "STORY"
STATE_ROOM = "ROOM"

BOOK_SLOT_LABELS = {slot: f"Book {idx + 1}" for idx, slot in enumerate(BOOK_SLOTS)}

# The two ring slots draw from the same "ring" catalog category; every
# other slot has its own dedicated pool.
SLOT_CATEGORY = {
    "helmet": "helmet", "armor": "armor", "pants": "pants", "sandals": "sandals",
    "left_hand": "left_hand", "right_hand": "right_hand", "necklace": "necklace",
    "ring_1": "ring", "ring_2": "ring",
}
SLOT_LABELS = {
    "helmet": "Helmet", "armor": "Armor", "pants": "Pants", "sandals": "Sandals",
    "left_hand": "Left Hand", "right_hand": "Right Hand", "necklace": "Necklace",
    "ring_1": "Ring 1", "ring_2": "Ring 2",
}
EMPTY_SLOT_LABEL = "-- Empty --"

TRAVEL_STEP = 0.045
MENU_OPTIONS = ["Unit", "Story", "Close"]

PANEL_BG = (18, 18, 30)
PANEL_BORDER = CURSOR_COLOR
TEXT_MAIN = (235, 235, 235)
TEXT_DIM = (150, 150, 160)
TEAM_COLOR = (110, 190, 255)
# Battle stages red, story nodes (a visual-novel scene, no battle yet - see
# story.py) gold; both are entered with Enter / a second click. Towns are
# path junctions; library and party rooms are houses with a one-time reward.
NODE_COLORS = {"stage": (206, 78, 52), "story": (222, 170, 48)}
WAYPOINT_COLOR = (90, 140, 200)
ROOM_TYPES = {"library", "party"}
ROOM_ROOF = {"library": (60, 104, 186), "party": (196, 58, 58)}
ROOM_GLYPH = {"library": "Preach", "party": "Breaking Bread"}
GRASS = ((112, 168, 72), (104, 158, 66))
ROAD = (232, 204, 140)
ROAD_EDGE = (150, 116, 64)
INK = (40, 28, 20)


def node_at_pos(pos):
    px, py = pos
    for node_id, node in NODES.items():
        nx, ny = node["pos"]
        if abs(px - nx) <= NODE_HALF and abs(py - ny) <= NODE_HALF:
            return node_id
    return None


def pick_neighbor_by_direction(current_id, dx, dy):
    cx, cy = NODES[current_id]["pos"]
    best_id = None
    best_score = 0.35
    for neighbor_id in NODES[current_id]["connections"]:
        nx, ny = NODES[neighbor_id]["pos"]
        vx, vy = nx - cx, ny - cy
        dist = math.hypot(vx, vy)
        if dist == 0:
            continue
        score = (vx / dist) * dx + (vy / dist) * dy
        if score > best_score:
            best_score = score
            best_id = neighbor_id
    return best_id


# The painted landscape under the roads: a meadow, the Mediterranean along
# the west with its beach, mountains to the east, and bushes, olive trees,
# flowers and rocks dotted about wherever there's no road or square.
MEADOW = (120, 176, 78)
MEADOW_LIGHT = (138, 190, 88)
MEADOW_DARK = (104, 158, 68)
SEA = (64, 146, 198)
SEA_DEEP = (44, 112, 170)
SAND = (232, 214, 160)
FOAM = (236, 246, 250)
LEAF = (66, 128, 52)
LEAF_DARK = (38, 84, 34)
LEAF_LIGHT = (112, 170, 82)
OLIVE = (124, 148, 92)
BARK = (110, 76, 46)
ROCK = (150, 146, 136)
MOUNTAIN = (150, 128, 104)
MOUNTAIN_SHADE = (118, 98, 80)
SNOW = (246, 246, 240)
FLOWER_COLORS = [(250, 250, 240), (250, 214, 70), (236, 120, 150), (180, 140, 230)]
SCENERY_CLEARANCE = 54    # how far decorations keep from a road's centre line
_background_cache = {}


def shoreline_x(y):
    """Where the sea meets the land, at screen row y."""
    return 150 + 42 * math.sin(y / 115) + 18 * math.sin(y / 41 + 1.3)


def _soft_blob(surface, color, center, radius, alpha):
    blob = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(blob, (*color, alpha), (radius, radius), radius)
    surface.blit(blob, (center[0] - radius, center[1] - radius))


def _shadow(surface, x, y, w, h):
    shade = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(shade, (20, 40, 10, 70), shade.get_rect())
    surface.blit(shade, (x - w // 2, y - h // 2))


def _bush(surface, x, y, rng):
    _shadow(surface, x, y + 9, 40, 12)
    for dx, dy, r in ((-9, 2, 9), (9, 2, 9), (0, -4, 11)):
        pygame.draw.circle(surface, LEAF_DARK, (x + dx, y + dy), r + 2)
    for dx, dy, r in ((-9, 2, 9), (9, 2, 9), (0, -4, 11)):
        pygame.draw.circle(surface, LEAF, (x + dx, y + dy), r)
    pygame.draw.circle(surface, LEAF_LIGHT, (x - 4, y - 8), 4)


def _tree(surface, x, y, rng, olive=False):
    _shadow(surface, x + 4, y + 14, 34, 10)
    pygame.draw.rect(surface, BARK, (x - 3, y - 2, 6, 16), border_radius=2)
    canopy = OLIVE if olive else LEAF
    for dx, dy, r in ((-8, -8, 10), (8, -8, 10), (0, -16, 12)):
        pygame.draw.circle(surface, LEAF_DARK, (x + dx, y + dy), r + 2)
    for dx, dy, r in ((-8, -8, 10), (8, -8, 10), (0, -16, 12)):
        pygame.draw.circle(surface, canopy, (x + dx, y + dy), r)
    pygame.draw.circle(surface, tuple(min(255, c + 30) for c in canopy), (x - 4, y - 20), 4)


def _flowers(surface, x, y, rng):
    color = rng.choice(FLOWER_COLORS)
    for _ in range(rng.randint(4, 7)):
        fx, fy = x + rng.randint(-14, 14), y + rng.randint(-8, 8)
        pygame.draw.line(surface, LEAF_DARK, (fx, fy), (fx, fy + 4), 1)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            pygame.draw.circle(surface, color, (fx + dx, fy + dy), 2)
        pygame.draw.circle(surface, (240, 180, 40), (fx, fy), 1)


def _rock(surface, x, y, rng):
    _shadow(surface, x, y + 6, 30, 9)
    w, h = rng.randint(18, 26), rng.randint(12, 16)
    pygame.draw.ellipse(surface, (90, 86, 80), (x - w // 2 - 1, y - h // 2 - 1, w + 2, h + 2))
    pygame.draw.ellipse(surface, ROCK, (x - w // 2, y - h // 2, w, h))
    pygame.draw.ellipse(surface, (190, 186, 176), (x - w // 4, y - h // 2 + 2, w // 3, h // 3))


def _mound(surface, x, y, rng):
    w, h = rng.randint(54, 76), rng.randint(26, 36)
    _shadow(surface, x, y + 2, w + 8, 12)
    dome = [(x + w / 2 * math.cos(a), y - h * math.sin(a)) for a in [math.pi * i / 20 for i in range(21)]]
    pygame.draw.polygon(surface, (98, 156, 64), dome)
    pygame.draw.lines(surface, LEAF_DARK, False, dome, 2)
    pygame.draw.ellipse(surface, MEADOW_LIGHT, (x - w // 4, y - h + 5, w // 3, h // 2))


def _mountain(surface, x, base, width, height, rng):
    peak = (x, base - height)
    left, right = (x - width // 2, base), (x + width // 2, base)
    pygame.draw.polygon(surface, MOUNTAIN, [left, peak, (x, base)])
    pygame.draw.polygon(surface, MOUNTAIN_SHADE, [peak, right, (x, base)])
    cap = 0.28
    cap_l = (x - width // 2 * cap, base - height * (1 - cap))
    cap_r = (x + width // 2 * cap, base - height * (1 - cap))
    pygame.draw.polygon(surface, SNOW, [cap_l, peak, cap_r, (x + 4, cap_l[1] + 6), (x - 6, cap_l[1] + 3)])
    pygame.draw.lines(surface, (86, 70, 56), False, [left, peak, right], 2)


def _distance_to_segment(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0 if length == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def build_world_background(nodes, seed=12):
    """The painted landscape for this node layout (cached)."""
    key = tuple(sorted((n, tuple(node["pos"])) for n, node in nodes.items()))
    if key in _background_cache:
        return _background_cache[key]
    rng = random.Random(seed)
    surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    surface.fill(MEADOW)
    # Light and shade drifting across the meadow.
    for _ in range(70):
        color = rng.choice((MEADOW_LIGHT, MEADOW_DARK))
        _soft_blob(surface, color, (rng.randint(0, SCREEN_WIDTH), rng.randint(0, SCREEN_HEIGHT)), rng.randint(40, 120), 70)
    for _ in range(900):
        x, y = rng.randint(0, SCREEN_WIDTH), rng.randint(0, SCREEN_HEIGHT)
        pygame.draw.line(surface, MEADOW_DARK, (x, y), (x + rng.choice((-2, 2)), y - 4), 1)

    # The sea to the west: deep water, a beach, foam along the edge.
    rows = range(0, SCREEN_HEIGHT + 8, 8)
    pygame.draw.polygon(surface, SAND, [(0, 0)] + [(shoreline_x(y) + 22, y) for y in rows] + [(0, SCREEN_HEIGHT)])
    pygame.draw.polygon(surface, SEA, [(0, 0)] + [(shoreline_x(y), y) for y in rows] + [(0, SCREEN_HEIGHT)])
    pygame.draw.polygon(surface, SEA_DEEP, [(0, 0)] + [(shoreline_x(y) - 70, y) for y in rows] + [(0, SCREEN_HEIGHT)])
    pygame.draw.lines(surface, FOAM, False, [(shoreline_x(y), y) for y in rows], 3)
    for _ in range(26):
        y = rng.randint(20, SCREEN_HEIGHT - 20)
        x = rng.uniform(10, shoreline_x(y) - 24)
        pygame.draw.arc(surface, FOAM, (x, y, 16, 8), math.pi * 0.1, math.pi * 0.9, 2)
        pygame.draw.arc(surface, FOAM, (x + 12, y, 16, 8), math.pi * 0.1, math.pi * 0.9, 2)

    # Mountains to the east, back row first.
    xs = [node["pos"][0] for node in nodes.values()]
    east = max(xs) + WORLD_MAP_CELL * 0.9
    for base, scale in ((SCREEN_HEIGHT * 0.3, 0.8), (SCREEN_HEIGHT * 0.62, 1.0), (SCREEN_HEIGHT * 0.95, 0.9)):
        x = east + rng.randint(0, 40)
        while x < SCREEN_WIDTH + 80:
            width = rng.randint(120, 170) * scale
            _mountain(surface, x, base + rng.randint(-30, 30), width, width * rng.uniform(0.7, 0.95), rng)
            x += width * 0.62

    # Scenery in the open ground, clear of the roads and squares.
    segments = []
    for node_id, node in nodes.items():
        for other in node["connections"]:
            if other in nodes:
                segments.append((node["pos"], nodes[other]["pos"]))
    centres = [node["pos"] for node in nodes.values()]
    step = WORLD_MAP_CELL // 2
    for gy in range(70, SCREEN_HEIGHT - 50, step):
        for gx in range(0, SCREEN_WIDTH, step):
            x, y = gx + rng.randint(-12, 12), gy + rng.randint(-12, 12)
            if x < shoreline_x(y) + 40 or x > east - 30 or rng.random() > 0.42:
                continue
            if any(_distance_to_segment((x, y), a, b) < SCENERY_CLEARANCE for a, b in segments):
                continue
            if any(math.hypot(x - cx, y - cy) < WORLD_MAP_CELL * 0.75 for cx, cy in centres):
                continue
            roll = rng.random()
            if roll < 0.32:
                _bush(surface, x, y, rng)
            elif roll < 0.52:
                _tree(surface, x, y, rng, olive=rng.random() < 0.6)
            elif roll < 0.74:
                _flowers(surface, x, y, rng)
            elif roll < 0.86:
                _rock(surface, x, y, rng)
            else:
                _mound(surface, x, y, rng)
    _background_cache[key] = surface
    return surface


def draw_world_background(surface):
    surface.blit(build_world_background(NODES), (0, 0))


def draw_road(surface, a, b):
    """A sandy road between two square centres, dotted at every square it
    crosses, like the paths on a Mario world map."""
    (ax, ay), (bx, by) = a, b
    width = round(WORLD_MAP_CELL * 0.34)
    rect = pygame.Rect(min(ax, bx) - width // 2, min(ay, by) - width // 2, abs(bx - ax) + width, abs(by - ay) + width)
    pygame.draw.rect(surface, ROAD_EDGE, rect.inflate(6, 6), border_radius=width // 2)
    pygame.draw.rect(surface, ROAD, rect, border_radius=width // 2)
    steps = max(1, round(max(abs(bx - ax), abs(by - ay)) / WORLD_MAP_CELL))
    for i in range(1, steps):
        dot = (ax + (bx - ax) * i / steps, ay + (by - ay) * i / steps)
        pygame.draw.circle(surface, ROAD_EDGE, dot, 5)


def draw_square(surface, font, pos, color, label, current, cleared):
    half = round(NODE_HALF)
    rect = pygame.Rect(0, 0, half * 2, half * 2)
    rect.center = pos
    pygame.draw.rect(surface, INK, rect.move(0, 5), border_radius=10)        # drop shadow
    pygame.draw.rect(surface, color, rect, border_radius=10)
    pygame.draw.rect(surface, tuple(min(255, c + 60) for c in color), rect.inflate(-10, -10), 3, border_radius=8)
    pygame.draw.rect(surface, CURSOR_COLOR if current else INK, rect, 4 if current else 3, border_radius=10)
    text = get_font(34, bold=True).render(label, True, (255, 250, 236))
    surface.blit(get_font(34, bold=True).render(label, True, INK), text.get_rect(center=(pos[0] + 2, pos[1] + 2)))
    surface.blit(text, text.get_rect(center=pos))
    if cleared:
        tick = [(rect.right - 26, rect.top + 12), (rect.right - 18, rect.top + 20), (rect.right - 6, rect.top + 4)]
        pygame.draw.lines(surface, (255, 255, 255), False, tick, 5)


def draw_house(surface, pos, kind, current, used):
    half = round(NODE_HALF)
    x, y = pos
    roof_color = (120, 120, 120) if used else ROOM_ROOF[kind]
    wall = pygame.Rect(x - half + 8, y - half * 0.15, half * 2 - 16, half * 1.1)
    pygame.draw.rect(surface, INK, wall.move(0, 5))
    pygame.draw.rect(surface, (238, 226, 200) if not used else (170, 166, 158), wall)
    pygame.draw.rect(surface, INK, wall, 3)
    roof = [(x - half - 2, wall.top + 2), (x, y - half - 6), (x + half + 2, wall.top + 2)]
    pygame.draw.polygon(surface, roof_color, roof)
    pygame.draw.polygon(surface, CURSOR_COLOR if current else INK, roof, 4 if current else 3)
    glyph = icons.icon(ROOM_GLYPH[kind], round(half * 0.95), roof_color, disabled=used)
    surface.blit(glyph, glyph.get_rect(center=(x, wall.centery + 2)))


def draw_path_and_nodes(surface, font, current_node, visited, chapter_by_node=None, cleared=(), rooms_used=()):
    drawn_edges = set()
    for node_id, node in NODES.items():
        for neighbor_id in node["connections"]:
            edge = tuple(sorted((node_id, neighbor_id)))
            if edge not in drawn_edges:
                drawn_edges.add(edge)
                draw_road(surface, NODES[node_id]["pos"], NODES[neighbor_id]["pos"])

    chapter_by_node = chapter_by_node or {}
    for number, (node_id, node) in enumerate(NODES.items(), start=1):
        pos = node["pos"]
        is_current = node_id == current_node
        if node["type"] in ROOM_TYPES:
            draw_house(surface, pos, node["type"], is_current, node_id in rooms_used)
        elif node["type"] in NODE_COLORS:
            chapter = chapter_by_node.get(node_id)
            label = str(chapter["chapter"]) if chapter else "!"
            color = NODE_COLORS[node["type"]]
            if node_id not in visited:
                color = tuple(int(c * 0.7) for c in color)
            draw_square(surface, font, pos, color, label, is_current, node_id in cleared)
        else:
            # A town: a junction stone on the road.
            pygame.draw.circle(surface, INK, (pos[0], pos[1] + 3), 17)
            pygame.draw.circle(surface, WAYPOINT_COLOR, pos, 15)
            pygame.draw.circle(surface, CURSOR_COLOR if is_current else (230, 230, 230), pos, 15, 3)


def draw_node_tag(surface, font, node, pos):
    """The node's name on a small tag just below its square (the hero's
    marker stands on top of it)."""
    text = font.render(node["name"], True, (255, 250, 236))
    tag = text.get_rect(midtop=(pos[0], pos[1] + NODE_HALF + 12)).inflate(16, 8)
    tag.clamp_ip(surface.get_rect())
    pygame.draw.rect(surface, PANEL_BG, tag, border_radius=8)
    pygame.draw.rect(surface, PANEL_BORDER, tag, 2, border_radius=8)
    surface.blit(text, text.get_rect(center=tag.center))


def draw_room_popup(surface, font, popup, frame=None):
    panel = pygame.Rect(0, 0, 820, 140 + 34 * max(1, len(popup["lines"])))
    panel.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
    draw_panel_bg(surface, panel, frame)
    inner = frame_content_rect(panel, frame) if frame else panel.inflate(-32, -32)
    surface.blit(get_font(30, bold=True).render(popup["title"], True, CURSOR_COLOR), (inner.x + 8, inner.y + 4))
    words, line, y = popup["text"].split(), "", inner.y + 46
    for word in words:
        trial = f"{line} {word}".strip()
        if font.size(trial)[0] > inner.width - 16:
            surface.blit(font.render(line, True, TEXT_MAIN), (inner.x + 8, y))
            line, y = word, y + 26
        else:
            line = trial
    surface.blit(font.render(line, True, TEXT_MAIN), (inner.x + 8, y))
    y += 40
    for entry in popup["lines"]:
        surface.blit(font.render(entry, True, (255, 215, 0)), (inner.x + 24, y))
        y += 30
    hint = font.render("[Click / Enter] Continue", True, TEXT_DIM)
    surface.blit(hint, hint.get_rect(bottomright=(inner.right - 8, inner.bottom - 2)))


TROOP_MARKER_SIZE = (252, 126)


def draw_troop_marker(surface, leader_icon, pos, bob_offset):
    x, y = pos
    y += bob_offset
    if leader_icon:
        # Stood at the back of the square, so its number still shows.
        rect = leader_icon.get_rect(midbottom=(x, y - 12))
        surface.blit(leader_icon, rect)
    else:
        pygame.draw.circle(surface, TEAM_COLOR, (int(x), int(y - 20)), 14)
        pygame.draw.circle(surface, (255, 255, 255), (int(x), int(y - 20)), 14, 2)


def draw_hint_bar(surface, font, text):
    panel = pygame.Rect(0, SCREEN_HEIGHT - 40, SCREEN_WIDTH, 40)
    pygame.draw.rect(surface, PANEL_BG, panel)
    pygame.draw.rect(surface, PANEL_BORDER, panel, 1)
    surface.blit(font.render(text, True, TEXT_MAIN), (16, panel.y + 10))


def draw_tooltip(surface, font, text, pos):
    """A small hover tooltip near the cursor, explaining what an attribute
    actually does in battle. Kept flat/plain rather than the ornate wooden
    frame - a tiny popup doesn't have room for a ~30px wood border without
    crowding the text, and this matches the other small HUD elements
    (menu button, hint bar) that stay flat by design."""
    padding = 8
    max_width = 260
    words = text.split()
    lines = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if font.size(candidate)[0] <= max_width:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    line_surfs = [font.render(l, True, TEXT_MAIN) for l in lines]

    box_width = max(s.get_width() for s in line_surfs) + padding * 2
    box_height = sum(s.get_height() for s in line_surfs) + padding * 2
    x, y = pos[0] + 16, pos[1] + 16
    x = min(x, SCREEN_WIDTH - box_width - 8)
    y = min(y, SCREEN_HEIGHT - box_height - 8)
    box = pygame.Rect(x, y, box_width, box_height)

    pygame.draw.rect(surface, (10, 10, 18), box)
    pygame.draw.rect(surface, PANEL_BORDER, box, 1)
    for idx, line_surf in enumerate(line_surfs):
        surface.blit(line_surf, (box.x + padding, box.y + padding + idx * line_surf.get_height()))


def draw_panel_bg(surface, rect, frame):
    """The ornate wooden frame (cut from the user's frame_example.jpg
    reference) when available, else the plain flat panel it replaces."""
    if frame:
        draw_nine_slice_panel(surface, rect, frame)
    else:
        pygame.draw.rect(surface, PANEL_BG, rect)
        pygame.draw.rect(surface, PANEL_BORDER, rect, 2)


def command_menu_layout(options, frame=None):
    # Sized generously (rather than hugging the text tightly) so the ornate
    # frame's ~110px corners always leave a real interior to draw into -
    # see _frame_corner_size in assets.py.
    width, height = 320, 240 + len(options) * 34
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(mx + 14, my + 40, width - 28, height - 54)
    option_rects = [pygame.Rect(content.x, content.y + 34 + idx * 34, content.width, 30) for idx in range(len(options))]
    return panel_rect, option_rects


def draw_command_menu(surface, font, options, index, title, frame=None):
    panel_rect, option_rects = command_menu_layout(options, frame)
    draw_panel_bg(surface, panel_rect, frame)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(panel_rect.x + 14, panel_rect.y + 40, panel_rect.width - 28, panel_rect.height - 54)
    surface.blit(font.render(title, True, PANEL_BORDER), (content.x, content.y))
    for idx, (opt, rect) in enumerate(zip(options, option_rects)):
        color = PANEL_BORDER if idx == index else TEXT_MAIN
        pointer = " -> " if idx == index else "    "
        surface.blit(font.render(f"{pointer}{opt}", True, color), (rect.x, rect.y))


def story_list_layout(chapters, frame=None):
    width, height = 900, 250 + len(chapters) * 60
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(mx + 14, my + 40, width - 28, height - 54)
    row_rects = [pygame.Rect(content.x - 6, content.y + 40 + idx * 60, content.width + 12, 52) for idx in range(len(chapters))]
    return panel_rect, row_rects


def draw_story_list(surface, font, chapters, heard, index, frame=None):
    """The stories in order, to replay the ones already heard (`heard` holds
    the node ids of those)."""
    panel_rect, row_rects = story_list_layout(chapters, frame)
    draw_panel_bg(surface, panel_rect, frame)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(panel_rect.x + 14, panel_rect.y + 40, panel_rect.width - 28, panel_rect.height - 54)
    surface.blit(font.render("STORY - replay a story you have heard", True, PANEL_BORDER), (content.x, content.y))
    for idx, (chapter, rect) in enumerate(zip(chapters, row_rects)):
        selected = idx == index
        if selected:
            pygame.draw.rect(surface, (60, 50, 30), rect)
            pygame.draw.rect(surface, PANEL_BORDER, rect, 1)
        unlocked = chapter["node_id"] in heard
        title = f"{chapter['chapter']}. {chapter['title']}" if unlocked else f"{chapter['chapter']}. ???"
        surface.blit(font.render(title, True, (PANEL_BORDER if selected else TEXT_MAIN) if unlocked else TEXT_DIM), (rect.x + 12, rect.y + 4))
        detail = chapter["passage"] if unlocked else f"Not yet heard - travel to {NODES.get(chapter['node_id'], {}).get('name', '?')}"
        surface.blit(font.render(detail, True, TEXT_DIM), (rect.x + 12, rect.y + 27))
    surface.blit(font.render("[Enter / Click] Replay   [Esc] Back", True, TEXT_DIM), (content.x, content.bottom - 24))


UNIT_LIST_ROWS = 12      # per column; a bigger company spills into a second
UNIT_LIST_COLUMN = 520


def unit_list_columns(units):
    return max(1, -(-len(units) // UNIT_LIST_ROWS))


def unit_list_layout(units, frame=None):
    # Wide enough that after the ~110px frame border eats into both sides,
    # each column's rows (portrait + name/class + faith/stamina) have room.
    columns = unit_list_columns(units)
    rows = min(len(units), UNIT_LIST_ROWS)
    width, height = 160 + UNIT_LIST_COLUMN * columns, 240 + max(1, rows) * 46
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(mx + 14, my + 40, width - 28, height - 54)
    column_width = content.width // columns
    row_rects = [pygame.Rect(content.x - 6 + (idx // UNIT_LIST_ROWS) * column_width,
                             content.y + 34 + (idx % UNIT_LIST_ROWS) * 46 - 4, column_width + 4, 40)
                 for idx in range(len(units))]
    return panel_rect, row_rects


def draw_unit_list(surface, font, units, portraits, index, frame=None, benched=()):
    panel_rect, row_rects = unit_list_layout(units, frame)
    draw_panel_bg(surface, panel_rect, frame)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(panel_rect.x + 14, panel_rect.y + 40, panel_rect.width - 28, panel_rect.height - 54)
    surface.blit(font.render(f"UNIT  -  your company of {len(units)}", True, PANEL_BORDER), (content.x, content.y))

    for idx, unit in enumerate(units):
        row = row_rects[idx]
        x, row_y = row.x + 6, row.y + 4
        selected = idx == index
        if selected:
            pygame.draw.rect(surface, (35, 35, 55), row)
        portrait = portraits.get(unit.name)
        if portrait:
            thumb = pygame.transform.smoothscale(portrait, (56, 28))
            if unit.name in benched:
                thumb.set_alpha(110)
            surface.blit(thumb, (x, row_y))
        name_color = PANEL_BORDER if selected else (TEXT_DIM if unit.name in benched else TEXT_MAIN)
        pointer = "->" if selected else "  "
        surface.blit(font.render(f"{pointer} {unit.name}", True, name_color), (x + 66, row_y))
        surface.blit(font.render("Benched" if unit.name in benched else unit.char_class, True, TEXT_DIM), (x + 66, row_y + 18))
        stats = font.render(f"Faith {round(unit.faith):3}", True, TEAM_COLOR)
        surface.blit(stats, (x + 236, row_y + 6))
        draw_stamina_dots(surface, x + 246 + stats.get_width(), row_y + 10, unit.mp, unit.max_mp, radius=5, gap=3)


# Display labels for stats shown to the player. Magic Attack/Magic Defense
# are renamed to Speech/Resist since what they actually do (see apply_preach
# and physical_hit_chance in game_logic.py) is boost preaching/healing and
# resist being struck - not a "magic damage" stat this game doesn't have.
# Every other stat just gets its key title-cased.
STAT_DISPLAY_LABELS = {
    "magic_attack": "Speech",
    "magic_defense": "Resist",
}


def stat_label(stat_key):
    return STAT_DISPLAY_LABELS.get(stat_key, stat_key.replace("_", " ").title())


# Every attribute shown on the Unit Detail screen now has a real effect in
# battle (see game_logic.py's physical_hit_chance, apply_preach,
# apply_skill_status and apply_item_effect) - these are the hover tooltips
# that explain what each one actually does, keyed to the same labels used
# in stat_hover_rects below.
STAT_TOOLTIPS = {
    "faith": "Doubles as this unit's health - reaching 0 removes them from battle. Preaching an enemy's Faith up to the cap converts them to your side.",
    "mp": "Stamina points: skills marked with a dot spend one. You regain one each turn; Myrrh restores them all.",
    "magic_attack": "Adds directly onto this unit's effective Faith when it Preaches or Heals another unit, making both stronger.",
    "magic_defense": "This unit's armor - reduces the chance an enemy's Physical attack lands on them.",
    "bravery": "A chance, once per this unit's own turn, to catch a surge of Morale - permanently +5 Faith, +1 Move, +1 Jump, +5 Speed for the rest of the battle.",
    "patience": "Grants a chance to simply shrug off a Snare or Stun inflicted by an enemy's skill.",
    "love": "Deepens this unit's compassion for others - boosts the Faith restored by their Ankh revivals and Mustard Seed blessings.",
}


def unit_detail_layout(frame=None):
    # +220 on each dimension vs. the original 520x420 tight design, so
    # after the ~110px frame border the interior is exactly that original
    # size again - every offset below can stay the same, just anchored to
    # the interior's corner instead of the panel's.
    width, height = 740, 640
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(mx + 110, my + 110, width - 220, height - 220)
    equip_button = pygame.Rect(content.x + content.width - 140, content.y + content.height - 34, 124, 26)
    books_button = pygame.Rect(equip_button.x - 134, equip_button.y, 124, 26)
    bench_button = pygame.Rect(books_button.x - 134, equip_button.y, 124, 26)

    cx, cy = content.x, content.y
    # Hit-testable rects for the hover tooltips - shared with draw_unit_detail
    # so the tooltip zone always matches exactly what's drawn where.
    stat_hover_rects = {
        "faith": pygame.Rect(cx + 170, cy + 82, 220, 20),
        "mp": pygame.Rect(cx + 170, cy + 102, 220, 20),
    }
    stat_keys = ["magic_attack", "magic_defense", "bravery", "patience", "love"]
    col_x = [cx + 16, cx + 270]
    for idx, key in enumerate(stat_keys):
        col = idx // 3
        row = idx % 3
        y = cy + 172 + row * 26
        stat_hover_rects[key] = pygame.Rect(col_x[col], y - 2, 230, 22)

    return panel_rect, equip_button, books_button, stat_hover_rects, bench_button


def draw_unit_detail(surface, font, unit, portraits, frame=None, benched=False, bio=""):
    panel_rect, equip_button, books_button, stat_hover_rects, bench_button = unit_detail_layout(frame)
    draw_panel_bg(surface, panel_rect, frame)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(panel_rect.x + 110, panel_rect.y + 110, panel_rect.width - 220, panel_rect.height - 220)
    cx, cy, width, height = content.x, content.y, content.width, content.height
    pygame.draw.line(surface, PANEL_BORDER, (cx, cy + 46), (cx + width, cy + 46), 1)

    portrait = portraits.get(unit.name)
    if portrait:
        thumb = pygame.transform.smoothscale(portrait, (140, 70))
        surface.blit(thumb, (cx + 16, cy + 60))

    surface.blit(font.render(unit.name, True, PANEL_BORDER), (cx + 16, cy + 12))
    surface.blit(font.render(unit.char_class, True, TEXT_DIM), (cx + 170, cy + 62))
    surface.blit(font.render(f"Faith  {round(unit.faith):3} / {FAITH_CAP}", True, (255, 215, 0)), (cx + 170, cy + 84))
    stamina = font.render("Stamina", True, (120, 170, 240))
    surface.blit(stamina, (cx + 170, cy + 104))
    draw_stamina_dots(surface, cx + 180 + stamina.get_width(), cy + 106, unit.mp, unit.max_mp, radius=6)

    pygame.draw.line(surface, (70, 70, 85), (cx + 16, cy + 150), (cx + width - 16, cy + 150), 1)

    stat_keys_display = ["magic_attack", "magic_defense", "bravery", "patience", "love"]
    for key in stat_keys_display:
        rect = stat_hover_rects[key]
        surface.blit(font.render(f"{stat_label(key):16}", True, TEXT_DIM), (rect.x, rect.y + 2))
        surface.blit(font.render(f"{getattr(unit, key)}", True, TEXT_MAIN), (rect.x + 190, rect.y + 2))

    pygame.draw.line(surface, (70, 70, 85), (cx + 16, cy + 288), (cx + width - 16, cy + 288), 1)
    surface.blit(font.render("Skills", True, PANEL_BORDER), (cx + 16, cy + 300))
    skills_text = "   ".join(unit.skills) if unit.skills else "-"
    surface.blit(font.render(skills_text, True, TEXT_MAIN), (cx + 16, cy + 324))

    surface.blit(font.render("[Enter / Esc] Back", True, TEXT_DIM), (cx + 16, cy + height - 28))

    pygame.draw.rect(surface, PANEL_BG, equip_button)
    pygame.draw.rect(surface, PANEL_BORDER, equip_button, 2)
    label = font.render("[E] Equip", True, PANEL_BORDER)
    surface.blit(label, label.get_rect(center=equip_button.center))

    pygame.draw.rect(surface, PANEL_BG, books_button)
    pygame.draw.rect(surface, PANEL_BORDER, books_button, 2)
    books_label = font.render("[B] Books", True, PANEL_BORDER)
    surface.blit(books_label, books_label.get_rect(center=books_button.center))

    # The leader always goes; anyone else can sit a battle out.
    if unit.name != LEADER:
        pygame.draw.rect(surface, PANEL_BG, bench_button)
        pygame.draw.rect(surface, PANEL_BORDER, bench_button, 2)
        bench_label = font.render("[D] Deploy" if benched else "[D] Bench", True, PANEL_BORDER)
        surface.blit(bench_label, bench_label.get_rect(center=bench_button.center))

    # Who they are, word-wrapped under the skills.
    words, line, y = bio.split(), "", cy + 356
    for word in words:
        trial = f"{line} {word}".strip()
        if font.size(trial)[0] > width - 32:
            surface.blit(font.render(line, True, TEXT_DIM), (cx + 16, y))
            line, y = word, y + 22
        else:
            line = trial
    if line:
        surface.blit(font.render(line, True, TEXT_DIM), (cx + 16, y))


def cycle_equipment(unit, slot_key, direction, equipment_pools):
    """Moves the item equipped in slot_key forward/backward through that
    slot's pool (with an explicit empty option at the front)."""
    pool = [None] + equipment_pools.get(SLOT_CATEGORY[slot_key], [])
    current = unit.equipment.get(slot_key)
    current_index = pool.index(current) if current in pool else 0
    unit.equipment[slot_key] = pool[(current_index + direction) % len(pool)]


def equipped_stat_totals(unit, equipment_registry):
    totals = {}
    for item_name in unit.equipment.values():
        item = equipment_registry.get(item_name) if item_name else None
        if not item:
            continue
        for stat, amount in item["stats"].items():
            totals[stat] = totals.get(stat, 0) + amount
    return totals


def equipment_screen_layout(frame=None):
    # +220 on each dimension vs. the original tight design, same trick as
    # unit_detail_layout - the interior ends up exactly the original size.
    width = 840
    height = 100 + len(UNIT_EQUIPMENT_SLOTS) * 36 + 70 + 220
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(mx + 110, my + 110, width - 220, height - 220)
    cx, cy = content.x, content.y
    row_rects = [pygame.Rect(cx + 16, cy + 90 + idx * 36, content.width - 32, 30) for idx in range(len(UNIT_EQUIPMENT_SLOTS))]
    left_arrows = [pygame.Rect(r.right - 210, r.y, 26, r.height) for r in row_rects]
    right_arrows = [pygame.Rect(r.right - 26, r.y, 26, r.height) for r in row_rects]
    return panel_rect, row_rects, left_arrows, right_arrows


def draw_equipment_screen(surface, font, unit, portraits, slot_index, equipment_registry, frame=None):
    panel_rect, row_rects, left_arrows, right_arrows = equipment_screen_layout(frame)
    draw_panel_bg(surface, panel_rect, frame)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(panel_rect.x + 110, panel_rect.y + 110, panel_rect.width - 220, panel_rect.height - 220)
    cx, cy, width, height = content.x, content.y, content.width, content.height
    pygame.draw.line(surface, PANEL_BORDER, (cx, cy + 46), (cx + width, cy + 46), 1)

    portrait = portraits.get(unit.name)
    if portrait:
        thumb = pygame.transform.smoothscale(portrait, (100, 50))
        surface.blit(thumb, (cx + 16, cy + 56))
    surface.blit(font.render(f"{unit.name} - Equipment", True, PANEL_BORDER), (cx + 16, cy + 12))
    surface.blit(font.render(unit.char_class, True, TEXT_DIM), (cx + 130, cy + 62))

    for idx, slot_key in enumerate(UNIT_EQUIPMENT_SLOTS):
        row = row_rects[idx]
        selected = idx == slot_index
        if selected:
            pygame.draw.rect(surface, (35, 35, 55), row)
        item_name = unit.equipment.get(slot_key)
        item_text = item_name if item_name else EMPTY_SLOT_LABEL
        label_color = PANEL_BORDER if selected else TEXT_MAIN
        pointer = "-> " if selected else "   "
        surface.blit(font.render(f"{pointer}{SLOT_LABELS[slot_key]}", True, label_color), (row.x, row.y + 4))
        surface.blit(font.render(item_text, True, TEAM_COLOR if item_name else TEXT_DIM), (row.x + 190, row.y + 4))

        arrow_color = PANEL_BORDER if selected else TEXT_DIM
        surface.blit(font.render("<", True, arrow_color), left_arrows[idx].topleft)
        surface.blit(font.render(">", True, arrow_color), right_arrows[idx].topleft)

    equipped_item = unit.equipment.get(UNIT_EQUIPMENT_SLOTS[slot_index])
    description = ""
    if equipped_item and equipped_item in equipment_registry:
        description = equipment_registry[equipped_item]["description"]
    desc_y = cy + 90 + len(UNIT_EQUIPMENT_SLOTS) * 36 + 6
    surface.blit(font.render(description, True, TEXT_DIM), (cx + 16, desc_y))

    totals = equipped_stat_totals(unit, equipment_registry)
    totals_text = "  ".join(f"+{amount} {stat_label(stat)}" for stat, amount in totals.items()) or "No bonuses equipped."
    surface.blit(font.render(totals_text, True, (255, 215, 0)), (cx + 16, cy + height - 50))
    surface.blit(font.render("[Left/Right] Change item   [Up/Down] Select slot   [Esc] Back", True, TEXT_DIM), (cx + 16, cy + height - 26))


def cycle_book(unit, slot_key, direction, book_pool):
    """Moves the book equipped in slot_key forward/backward through the
    full book catalog - unlike equipment, every book slot is generic and
    accepts any book. Swapping to a different book resets that slot's
    turns-held/reading-level/gain progress, since it's now a different book
    being read from scratch."""
    pool = [None] + book_pool
    current = unit.books.get(slot_key)
    current_index = pool.index(current) if current in pool else 0
    unit.books[slot_key] = pool[(current_index + direction) % len(pool)]
    unit.book_turns[slot_key] = 0
    unit.book_gain[slot_key] = 0


def book_stat_totals(unit, books_registry):
    """Total stat gain accrued so far across all 5 book slots, grouped by
    stat - the Daily Devotion equivalent of equipped_stat_totals."""
    totals = {}
    for slot, book_name in unit.books.items():
        if not book_name:
            continue
        book = books_registry.get(book_name)
        gain = unit.book_gain.get(slot, 0)
        if not book or not gain:
            continue
        totals[book["stat"]] = totals.get(book["stat"], 0) + gain
    return totals


def books_screen_layout(frame=None):
    # Same "+220 both dimensions" trick as equipment_screen_layout so the
    # interior lands back at the original tight-margin size.
    width = 840
    height = 100 + len(BOOK_SLOTS) * 36 + 70 + 220
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(mx + 110, my + 110, width - 220, height - 220)
    cx, cy = content.x, content.y
    row_rects = [pygame.Rect(cx + 16, cy + 90 + idx * 36, content.width - 32, 30) for idx in range(len(BOOK_SLOTS))]
    left_arrows = [pygame.Rect(r.right - 210, r.y, 26, r.height) for r in row_rects]
    right_arrows = [pygame.Rect(r.right - 26, r.y, 26, r.height) for r in row_rects]
    return panel_rect, row_rects, left_arrows, right_arrows


def draw_books_screen(surface, font, unit, portraits, slot_index, books_registry, frame=None):
    panel_rect, row_rects, left_arrows, right_arrows = books_screen_layout(frame)
    draw_panel_bg(surface, panel_rect, frame)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(panel_rect.x + 110, panel_rect.y + 110, panel_rect.width - 220, panel_rect.height - 220)
    cx, cy, width, height = content.x, content.y, content.width, content.height
    pygame.draw.line(surface, PANEL_BORDER, (cx, cy + 46), (cx + width, cy + 46), 1)

    portrait = portraits.get(unit.name)
    if portrait:
        thumb = pygame.transform.smoothscale(portrait, (100, 50))
        surface.blit(thumb, (cx + 16, cy + 56))
    surface.blit(font.render(f"{unit.name} - Daily Devotion Books", True, PANEL_BORDER), (cx + 16, cy + 12))
    surface.blit(font.render(unit.char_class, True, TEXT_DIM), (cx + 130, cy + 62))

    for idx, slot_key in enumerate(BOOK_SLOTS):
        row = row_rects[idx]
        selected = idx == slot_index
        if selected:
            pygame.draw.rect(surface, (35, 35, 55), row)
        book_name = unit.books.get(slot_key)
        if book_name:
            turns = unit.book_turns.get(slot_key, 0)
            level = reading_level(turns)
            item_text = f"{book_name}  [{level}, {turns} turns]"
        else:
            item_text = EMPTY_SLOT_LABEL
        label_color = PANEL_BORDER if selected else TEXT_MAIN
        pointer = "-> " if selected else "   "
        surface.blit(font.render(f"{pointer}{BOOK_SLOT_LABELS[slot_key]}", True, label_color), (row.x, row.y + 4))
        surface.blit(font.render(item_text, True, TEAM_COLOR if book_name else TEXT_DIM), (row.x + 90, row.y + 4))

        arrow_color = PANEL_BORDER if selected else TEXT_DIM
        surface.blit(font.render("<", True, arrow_color), left_arrows[idx].topleft)
        surface.blit(font.render(">", True, arrow_color), right_arrows[idx].topleft)

    equipped_book = unit.books.get(BOOK_SLOTS[slot_index])
    description = ""
    if equipped_book and equipped_book in books_registry:
        description = books_registry[equipped_book]["description"]
    desc_y = cy + 90 + len(BOOK_SLOTS) * 36 + 6
    surface.blit(font.render(description, True, TEXT_DIM), (cx + 16, desc_y))

    totals = book_stat_totals(unit, books_registry)
    totals_text = "  ".join(f"+{amount} {stat_label(stat)}" for stat, amount in totals.items()) or "No stat gains yet - carry books into battle to grow them."
    surface.blit(font.render(totals_text, True, (255, 215, 0)), (cx + 16, cy + height - 50))
    surface.blit(font.render("[Left/Right] Change book   [Up/Down] Select slot   [Esc] Back", True, TEXT_DIM), (cx + 16, cy + height - 26))


async def main(hero=None):
    """The world map. `hero` is the player's saved profile (see hero.py): the
    hero travels the map and joins every battle, and the stories heard and
    the places visited are saved back into it."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    required_files = ["map_layout.csv", "skills.csv", "items.csv", "equipment.csv", "characters.csv", "terrain_layout.csv", "game_settings.csv", "dialogues.csv"]
    if not all(os.path.exists(os.path.join(data_dir, filename)) for filename in required_files):
        generate_dummy_csv_files()

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("The Road to Jerusalem")
    bring_window_to_front()
    clock = pygame.time.Clock()
    font = get_font(22)

    ui_frame = load_nine_slice_frame()

    def play_theme():
        """The world map's theme (tools/generate_world_music.py), looping."""
        try:
            pygame.mixer.music.load(WORLD_THEME_PATH)
            pygame.mixer.music.set_volume(MUSIC_VOLUME)
            pygame.mixer.music.play(-1)
        except (pygame.error, OSError):
            pass
    play_theme()

    stage_manifest = load_stage_manifest()

    # Your company: the roster members recruited so far (see roster.py).
    # Older saves without a recruited list catch up from the scenes heard.
    roster = load_roster()
    roster_by_name = {c["name"]: c for c in roster}
    profile = hero or {}
    recruited = set(profile.get("recruited") or recruited_after(profile.get("heard", []), roster))
    benched = set(profile.get("bench", [])) & recruited
    units = [Unit(c) for c in roster if c["name"] in recruited]
    portraits = build_character_face_portraits(units, [])
    leader = units[0] if units else None
    leader_icon = None
    classes = load_classes_from_csv()
    if hero and hero.get("type") in classes:
        leader_icon = load_image_safe(hero_token(hero, classes[hero["type"]]["role"]))
        leader_icon = pygame.transform.smoothscale(leader_icon, TROOP_MARKER_SIZE) if leader_icon else None
    elif leader and portraits.get(leader.name):
        leader_icon = pygame.transform.smoothscale(portraits[leader.name], TROOP_MARKER_SIZE)

    equipment_registry = load_equipment_from_csv()
    equipment_pools = equipment_by_slot(equipment_registry)

    books_registry = load_books_from_csv()
    book_pool = sorted(books_registry.keys())

    rooms = load_world_map_rooms()
    base_item_uses = {name: data["uses"] for name, data in load_items_from_csv().items()}

    story = load_story()
    chapters = load_chapters()
    chapter_by_node = {c["node_id"]: c for c in chapters}
    hero_name = profile.get("name")
    heard = set(profile.get("heard", []))  # ids of the scenes played through
    # Rooms already visited, stages won, and gift items not yet used up.
    rooms_used = set(profile.get("rooms_used", []))
    cleared = set(profile.get("cleared", []))
    satchel_gifts = {name: count for name, count in profile.get("satchel", {}).items() if count > 0}
    # The party's progress (levels, EXP, books, equipment) between sessions.
    for u in units:
        saved = profile.get("party", {}).get(u.name)
        if saved:
            u.level, u.exp = saved.get("level", u.level), saved.get("exp", u.exp)
            u.books, u.book_turns, u.book_gain = saved.get("books", {}), saved.get("turns", {}), saved.get("gain", {})
            u.equipment = saved.get("equipment", u.equipment)
    room_popup = None

    state = STATE_MAP
    current_node = profile.get("node") if profile.get("node") in NODES else START_NODE
    visited = {n for n in profile.get("visited", []) if n in NODES} | {current_node}
    transition_from = None
    transition_to = None
    transition_progress = 0.0

    menu_index = 0
    unit_index = 0
    selected_unit = None
    equip_slot_index = 0
    book_slot_index = 0
    story_index = 0
    mouse_pos = (0, 0)

    menu_button = pygame.Rect(SCREEN_WIDTH - 130, 20, 110, 34)

    async def enter_battle(node_id):
        equipment_loadout = {u.name: dict(u.equipment) for u in units}
        book_loadout = {
            u.name: {"books": dict(u.books), "turns": dict(u.book_turns), "gain": dict(u.book_gain),
                     "level": u.level, "exp": u.exp}
            for u in units
        }
        party = [u.name for u in units if u.name not in benched]
        result = await run_battle(stage=stage_manifest.get(node_id), equipment_loadout=equipment_loadout,
                                  book_loadout=book_loadout, hero=hero, from_map=True, bonus_items=dict(satchel_gifts),
                                  party=party)
        # Base uses refill every battle; gifts last until they're used up
        # (the base uses go first).
        left = result.get("satchel", {})
        for name in list(satchel_gifts):
            satchel_gifts[name] = max(0, min(satchel_gifts[name], left.get(name, 0) - base_item_uses.get(name, 0)))
        if result["victory"]:
            cleared.add(node_id)
        progress = result["units"]
        if progress:
            for u in units:
                p = progress.get(u.name)
                if p:
                    u.books = p.get("books", u.books)
                    u.book_turns = p.get("turns", u.book_turns)
                    u.book_gain = p.get("gain", u.book_gain)
                    u.level = p.get("level", u.level)
                    u.exp = p.get("exp", u.exp)
        pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("The Road to Jerusalem")
        play_theme()
        save_progress()
        return result["victory"]

    def save_progress():
        if hero:
            party = {u.name: {"level": u.level, "exp": u.exp, "books": dict(u.books), "turns": dict(u.book_turns),
                              "gain": dict(u.book_gain), "equipment": dict(u.equipment)} for u in units}
            profile.update(heard=sorted(heard), node=current_node, visited=sorted(visited), rooms_used=sorted(rooms_used),
                           cleared=sorted(cleared), satchel={n: c for n, c in satchel_gifts.items() if c > 0}, party=party,
                           recruited=[u.name for u in units], bench=sorted(benched))
            save_profile(profile)

    def visit_room(node_id):
        """A library or party room's one-time reward. Returns the popup."""
        node, room = NODES[node_id], rooms.get(node_id, {})
        if node_id in rooms_used:
            return {"title": node["name"], "text": "You've already visited here. Its doors are closed for now.", "lines": []}
        lines = []
        turns = room.get("book_turns", 0)
        if turns:
            readers = [u for u in units if any(u.books.values())]
            for u in readers:
                before = sum(u.book_gain.values())
                for _ in range(turns):
                    apply_book_growth(u, books_registry)
                lines.append(f"{u.name}: +{turns} days of reading, +{sum(u.book_gain.values()) - before} to book stats")
            if not readers:
                return {"title": node["name"], "text": room.get("text", ""),
                        "lines": ["No one is carrying devotion books yet - equip some from Menu > Unit > Books, then come back."]}
        if room.get("exp"):
            for u in units:
                levels = gain_exp(u, room["exp"])
                lines.append(f"{u.name}: +{room['exp']} EXP" + (f"  - LEVEL UP to Lv {u.level}!" if levels else ""))
        for name, count in room.get("items", {}).items():
            satchel_gifts[name] = satchel_gifts.get(name, 0) + count
            lines.append(f"+{count} {name} for the satchel (kept until used)")
        rooms_used.add(node_id)
        save_progress()
        return {"title": node["name"], "text": room.get("text", ""), "lines": lines}

    def toggle_bench(unit):
        benched.symmetric_difference_update({unit.name})
        save_progress()

    def recruit(scene_id):
        """Whoever joins after this scene steps into the company. Returns the
        popup announcing them, or None."""
        present = {u.name for u in units}
        joining = [name for name in recruits_for(scene_id, roster) if name not in present]
        if not joining:
            return None
        newcomers = [Unit(roster_by_name[name]) for name in joining]
        units.extend(newcomers)
        order = list(roster_by_name)
        units.sort(key=lambda u: order.index(u.name))
        portraits.update(build_character_face_portraits(newcomers, []))
        if len(joining) == 1:
            return {"title": f"{joining[0]} joins your company!", "text": roster_by_name[joining[0]]["bio"], "lines": []}
        return {"title": "New companions join you!", "text": "From here on they walk the road with you:",
                "lines": [f"{name} - {roster_by_name[name]['class']}" for name in joining]}

    async def announce(popup):
        """Shows a popup over whatever is on screen until it's dismissed -
        so a recruit from a stage's opening scene is introduced before the
        battle rather than after it."""
        backdrop = screen.copy()
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.event.post(event)
                    return
                if ((event.type == pygame.MOUSEBUTTONDOWN and event.button == 1)
                        or (event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE))):
                    return
            screen.blit(backdrop, (0, 0))
            draw_room_popup(screen, font, popup, ui_frame)
            pygame.display.flip()
            clock.tick(60)
            await asyncio.sleep(0)

    async def play(scene_id):
        if await play_scene(screen, scene_id, hero_name=hero_name, story=story):
            heard.add(scene_id)
            popup = recruit(scene_id)
            save_progress()
            if popup:
                await announce(popup)

    async def enter_node(node_id):
        """A node's story: its intro scene, its battle (if it has one) and,
        after a victory, its outro. A stage's intro only plays the first
        time - the Story menu replays it."""
        intro, outro = scene_ids(node_id)
        is_stage = NODES[node_id]["type"] == "stage" and node_id in stage_manifest
        if not is_stage or intro not in heard:
            await play(intro)
        if not is_stage or await enter_battle(node_id):
            await play(outro)

    def chapter_heard(node_id):
        return any(scene in heard for scene in scene_ids(node_id))

    async def replay_chapter(chapter):
        for scene in scene_ids(chapter["node_id"]):
            if scene in heard:
                await play(scene)

    def open_story_list():
        nonlocal state, story_index
        state = STATE_STORY
        story_index = next((i for i, c in enumerate(chapters) if c["node_id"] == current_node), 0)

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        bob_offset = math.sin(pygame.time.get_ticks() / 250.0) * 4

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEMOTION:
                mouse_pos = event.pos

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state == STATE_MAP and menu_button.collidepoint(event.pos):
                    state = STATE_MENU
                    menu_index = 0
                elif state == STATE_ROOM:
                    state = STATE_MAP
                elif state == STATE_MAP:
                    clicked_node = node_at_pos(event.pos)
                    if clicked_node == current_node:
                        if NODES[current_node]["type"] in ROOM_TYPES:
                            room_popup = visit_room(current_node)
                            state = STATE_ROOM
                        elif NODES[current_node]["type"] in NODE_COLORS:
                            await enter_node(current_node)
                    elif clicked_node is not None and clicked_node in NODES[current_node]["connections"]:
                        transition_from = current_node
                        transition_to = clicked_node
                        transition_progress = 0.0
                        state = STATE_TRANSITION

                elif state == STATE_MENU:
                    panel_rect, option_rects = command_menu_layout(MENU_OPTIONS, ui_frame)
                    clicked = next((idx for idx, rect in enumerate(option_rects) if rect.collidepoint(event.pos)), None)
                    if clicked is not None:
                        menu_index = clicked
                        choice = MENU_OPTIONS[clicked]
                        if choice == "Unit":
                            state = STATE_UNIT_LIST
                            unit_index = 0
                        elif choice == "Story":
                            open_story_list()
                        elif choice == "Close":
                            state = STATE_MAP
                    elif not panel_rect.collidepoint(event.pos):
                        state = STATE_MAP

                elif state == STATE_STORY:
                    panel_rect, row_rects = story_list_layout(chapters, ui_frame)
                    clicked = next((idx for idx, rect in enumerate(row_rects) if rect.collidepoint(event.pos)), None)
                    if clicked is not None:
                        story_index = clicked
                        await replay_chapter(chapters[clicked])
                    elif not panel_rect.collidepoint(event.pos):
                        state = STATE_MENU

                elif state == STATE_UNIT_LIST:
                    panel_rect, row_rects = unit_list_layout(units, ui_frame)
                    clicked = next((idx for idx, rect in enumerate(row_rects) if rect.collidepoint(event.pos)), None)
                    if clicked is not None:
                        unit_index = clicked
                        selected_unit = units[clicked]
                        state = STATE_UNIT_DETAIL
                    elif not panel_rect.collidepoint(event.pos):
                        state = STATE_MENU
                        menu_index = 0

                elif state == STATE_UNIT_DETAIL:
                    _, equip_button, books_button, _, bench_button = unit_detail_layout(ui_frame)
                    if equip_button.collidepoint(event.pos):
                        state = STATE_EQUIPMENT
                        equip_slot_index = 0
                    elif books_button.collidepoint(event.pos):
                        state = STATE_BOOKS
                        book_slot_index = 0
                    elif bench_button.collidepoint(event.pos) and selected_unit.name != LEADER:
                        toggle_bench(selected_unit)
                    else:
                        state = STATE_UNIT_LIST

                elif state == STATE_EQUIPMENT:
                    panel_rect, row_rects, left_arrows, right_arrows = equipment_screen_layout(ui_frame)
                    left_hit = next((idx for idx, rect in enumerate(left_arrows) if rect.collidepoint(event.pos)), None)
                    right_hit = next((idx for idx, rect in enumerate(right_arrows) if rect.collidepoint(event.pos)), None)
                    row_hit = next((idx for idx, rect in enumerate(row_rects) if rect.collidepoint(event.pos)), None)
                    if left_hit is not None:
                        equip_slot_index = left_hit
                        cycle_equipment(selected_unit, UNIT_EQUIPMENT_SLOTS[left_hit], -1, equipment_pools)
                    elif right_hit is not None:
                        equip_slot_index = right_hit
                        cycle_equipment(selected_unit, UNIT_EQUIPMENT_SLOTS[right_hit], 1, equipment_pools)
                    elif row_hit is not None:
                        equip_slot_index = row_hit
                    elif not panel_rect.collidepoint(event.pos):
                        state = STATE_UNIT_DETAIL

                elif state == STATE_BOOKS:
                    panel_rect, row_rects, left_arrows, right_arrows = books_screen_layout(ui_frame)
                    left_hit = next((idx for idx, rect in enumerate(left_arrows) if rect.collidepoint(event.pos)), None)
                    right_hit = next((idx for idx, rect in enumerate(right_arrows) if rect.collidepoint(event.pos)), None)
                    row_hit = next((idx for idx, rect in enumerate(row_rects) if rect.collidepoint(event.pos)), None)
                    if left_hit is not None:
                        book_slot_index = left_hit
                        cycle_book(selected_unit, BOOK_SLOTS[left_hit], -1, book_pool)
                    elif right_hit is not None:
                        book_slot_index = right_hit
                        cycle_book(selected_unit, BOOK_SLOTS[right_hit], 1, book_pool)
                    elif row_hit is not None:
                        book_slot_index = row_hit
                    elif not panel_rect.collidepoint(event.pos):
                        state = STATE_UNIT_DETAIL

            elif event.type == pygame.KEYDOWN:
                if state == STATE_MAP:
                    if event.key == pygame.K_ESCAPE:
                        state = STATE_MENU
                        menu_index = 0
                    elif event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
                        dx, dy = {
                            pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1),
                            pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0),
                        }[event.key]
                        target = pick_neighbor_by_direction(current_node, dx, dy)
                        if target is not None:
                            transition_from = current_node
                            transition_to = target
                            transition_progress = 0.0
                            state = STATE_TRANSITION
                    elif event.key == pygame.K_RETURN:
                        if NODES[current_node]["type"] in ROOM_TYPES:
                            room_popup = visit_room(current_node)
                            state = STATE_ROOM
                        elif NODES[current_node]["type"] in NODE_COLORS:
                            await enter_node(current_node)

                elif state == STATE_ROOM:
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                        state = STATE_MAP

                elif state == STATE_MENU:
                    if event.key == pygame.K_UP:
                        menu_index = (menu_index - 1) % len(MENU_OPTIONS)
                    elif event.key == pygame.K_DOWN:
                        menu_index = (menu_index + 1) % len(MENU_OPTIONS)
                    elif event.key == pygame.K_ESCAPE:
                        state = STATE_MAP
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        choice = MENU_OPTIONS[menu_index]
                        if choice == "Unit":
                            state = STATE_UNIT_LIST
                            unit_index = 0
                        elif choice == "Story":
                            open_story_list()
                        elif choice == "Close":
                            state = STATE_MAP

                elif state == STATE_STORY:
                    if event.key == pygame.K_UP:
                        story_index = (story_index - 1) % max(1, len(chapters))
                    elif event.key == pygame.K_DOWN:
                        story_index = (story_index + 1) % max(1, len(chapters))
                    elif event.key == pygame.K_ESCAPE:
                        state = STATE_MENU
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and chapters:
                        await replay_chapter(chapters[story_index])

                elif state == STATE_UNIT_LIST:
                    if event.key == pygame.K_UP:
                        unit_index = (unit_index - 1) % max(1, len(units))
                    elif event.key == pygame.K_DOWN:
                        unit_index = (unit_index + 1) % max(1, len(units))
                    elif event.key == pygame.K_ESCAPE:
                        state = STATE_MENU
                        menu_index = 0
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and units:
                        selected_unit = units[unit_index]
                        state = STATE_UNIT_DETAIL

                elif state == STATE_UNIT_DETAIL:
                    if event.key == pygame.K_e:
                        state = STATE_EQUIPMENT
                        equip_slot_index = 0
                    elif event.key == pygame.K_b:
                        state = STATE_BOOKS
                        book_slot_index = 0
                    elif event.key == pygame.K_d and selected_unit.name != LEADER:
                        toggle_bench(selected_unit)
                    elif event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                        state = STATE_UNIT_LIST

                elif state == STATE_EQUIPMENT:
                    if event.key == pygame.K_UP:
                        equip_slot_index = (equip_slot_index - 1) % len(UNIT_EQUIPMENT_SLOTS)
                    elif event.key == pygame.K_DOWN:
                        equip_slot_index = (equip_slot_index + 1) % len(UNIT_EQUIPMENT_SLOTS)
                    elif event.key == pygame.K_LEFT:
                        cycle_equipment(selected_unit, UNIT_EQUIPMENT_SLOTS[equip_slot_index], -1, equipment_pools)
                    elif event.key == pygame.K_RIGHT:
                        cycle_equipment(selected_unit, UNIT_EQUIPMENT_SLOTS[equip_slot_index], 1, equipment_pools)
                    elif event.key == pygame.K_ESCAPE:
                        state = STATE_UNIT_DETAIL

                elif state == STATE_BOOKS:
                    if event.key == pygame.K_UP:
                        book_slot_index = (book_slot_index - 1) % len(BOOK_SLOTS)
                    elif event.key == pygame.K_DOWN:
                        book_slot_index = (book_slot_index + 1) % len(BOOK_SLOTS)
                    elif event.key == pygame.K_LEFT:
                        cycle_book(selected_unit, BOOK_SLOTS[book_slot_index], -1, book_pool)
                    elif event.key == pygame.K_RIGHT:
                        cycle_book(selected_unit, BOOK_SLOTS[book_slot_index], 1, book_pool)
                    elif event.key == pygame.K_ESCAPE:
                        state = STATE_UNIT_DETAIL

        if state == STATE_TRANSITION:
            transition_progress = min(1.0, transition_progress + TRAVEL_STEP)
            if transition_progress >= 1.0:
                current_node = transition_to
                visited.add(current_node)
                save_progress()
                transition_from = None
                transition_to = None
                state = STATE_MAP

        # --- DRAW ---
        draw_world_background(screen)
        draw_path_and_nodes(screen, font, current_node, visited, chapter_by_node, cleared, rooms_used)

        if state == STATE_TRANSITION:
            fx, fy = NODES[transition_from]["pos"]
            tx, ty = NODES[transition_to]["pos"]
            pos = (fx + (tx - fx) * transition_progress, fy + (ty - fy) * transition_progress)
        else:
            pos = NODES[current_node]["pos"]
        draw_troop_marker(screen, leader_icon, pos, bob_offset)
        if state in (STATE_MAP, STATE_ROOM):
            hovered = node_at_pos(mouse_pos)
            for tagged in {current_node, hovered} - {None}:
                draw_node_tag(screen, font, NODES[tagged], NODES[tagged]["pos"])

        pygame.draw.rect(screen, PANEL_BG, menu_button)
        pygame.draw.rect(screen, PANEL_BORDER, menu_button, 2)
        screen.blit(font.render("[Esc] Menu", True, TEXT_MAIN), (menu_button.x + 8, menu_button.y + 8))

        if state == STATE_MAP:
            node = NODES[current_node]
            chapter = chapter_by_node.get(current_node)
            if chapter:
                draw_hint_bar(screen, font, f"Click/Arrows: Travel   |   Click node again (or Enter) to begin Story {chapter['chapter']}: {chapter['title']}   |   [Esc] Menu")
            elif node["type"] == "stage":
                draw_hint_bar(screen, font, f"Click/Arrows: Travel   |   Click node again (or Enter) to begin battle at {node['name']}   |   [Esc] Menu")
            elif node["type"] in ROOM_TYPES:
                kind = "Library" if node["type"] == "library" else "Party Room"
                status = "visited" if current_node in rooms_used else "click again (or Enter) to go in"
                draw_hint_bar(screen, font, f"Click/Arrows: Travel   |   {node['name']} ({kind}) - {status}   |   [Esc] Menu")
            else:
                draw_hint_bar(screen, font, f"Click/Arrows: Travel   |   {node['name']} (Waypoint)   |   [Esc] Menu")
        elif state == STATE_ROOM and room_popup:
            draw_room_popup(screen, font, room_popup, ui_frame)
        elif state == STATE_MENU:
            draw_command_menu(screen, font, MENU_OPTIONS, menu_index, "MENU", ui_frame)
        elif state == STATE_STORY:
            draw_story_list(screen, font, chapters, {c["node_id"] for c in chapters if chapter_heard(c["node_id"])}, story_index, ui_frame)
        elif state == STATE_UNIT_LIST:
            draw_unit_list(screen, font, units, portraits, unit_index, ui_frame, benched)
        elif state == STATE_UNIT_DETAIL and selected_unit:
            draw_unit_detail(screen, font, selected_unit, portraits, ui_frame, selected_unit.name in benched,
                             roster_by_name.get(selected_unit.name, {}).get("bio", ""))
            _, _, _, stat_hover_rects, _ = unit_detail_layout(ui_frame)
            hovered_stat = next((key for key, rect in stat_hover_rects.items() if rect.collidepoint(mouse_pos)), None)
            if hovered_stat:
                draw_tooltip(screen, font, STAT_TOOLTIPS[hovered_stat], mouse_pos)
        elif state == STATE_EQUIPMENT and selected_unit:
            draw_equipment_screen(screen, font, selected_unit, portraits, equip_slot_index, equipment_registry, ui_frame)
        elif state == STATE_BOOKS and selected_unit:
            draw_books_screen(screen, font, selected_unit, portraits, book_slot_index, books_registry, ui_frame)

        pygame.display.flip()
        await asyncio.sleep(0)


if __name__ == "__main__":
    asyncio.run(main())
    pygame.quit()
    sys.exit()

import os
import sys
import math
import asyncio
import pygame

from scripts.config import SCREEN_WIDTH, SCREEN_HEIGHT, CURSOR_COLOR, FAITH_CAP
from scripts.data_editor import (
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
from scripts.game_logic import Unit, main as run_battle

# --- WORLD MAP DATA ---
# Node layout (screen position, type, which nodes connect to which) lives in
# data/world_map_nodes.csv so it can be tuned without touching code. Falls
# back to this hardcoded route (a small, mostly-linear path in the spirit of
# the Super Mario World overworld) if that file is ever missing/malformed.
_FALLBACK_NODES = {
    "jerusalem": {"pos": (352, 320),  "name": "Jerusalem",  "type": "stage", "connections": ["caesarea"]},
    "caesarea":  {"pos": (273, 570),  "name": "Caesarea",   "type": "town",  "connections": ["jerusalem", "antioch"]},
    "antioch":   {"pos": (609, 500),  "name": "Antioch",    "type": "stage", "connections": ["caesarea", "philippi", "corinth"]},
    "philippi":  {"pos": (727, 258),  "name": "Philippi",   "type": "stage", "connections": ["antioch", "troas"]},
    "corinth":   {"pos": (727, 695),  "name": "Corinth",    "type": "stage", "connections": ["antioch", "troas"]},
    "troas":     {"pos": (969, 438),  "name": "Troas",      "type": "town",  "connections": ["philippi", "corinth", "ephesus"]},
    "ephesus":   {"pos": (1266, 563), "name": "Ephesus",    "type": "stage", "connections": ["troas", "rome"]},
    "rome":      {"pos": (1406, 258), "name": "Rome",       "type": "stage", "connections": ["ephesus"]},
}
try:
    NODES, START_NODE = load_world_map_nodes()
    if not NODES:
        raise ValueError("world_map_nodes.csv produced no nodes")
except (OSError, ValueError, KeyError):
    NODES, START_NODE = _FALLBACK_NODES, "jerusalem"
NODE_CLICK_RADIUS = 26

STATE_MAP = "MAP"
STATE_TRANSITION = "TRANSITION"
STATE_MENU = "MENU"
STATE_UNIT_LIST = "UNIT_LIST"
STATE_UNIT_DETAIL = "UNIT_DETAIL"
STATE_EQUIPMENT = "EQUIPMENT"
STATE_BOOKS = "BOOKS"

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
MENU_OPTIONS = ["Unit", "Close"]

PANEL_BG = (18, 18, 30)
PANEL_BORDER = CURSOR_COLOR
TEXT_MAIN = (235, 235, 235)
TEXT_DIM = (150, 150, 160)
TEAM_COLOR = (110, 190, 255)


def node_at_pos(pos):
    px, py = pos
    for node_id, node in NODES.items():
        nx, ny = node["pos"]
        if math.hypot(px - nx, py - ny) <= NODE_CLICK_RADIUS:
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


def draw_path_and_nodes(surface, font, current_node, visited):
    drawn_edges = set()
    for node_id, node in NODES.items():
        for neighbor_id in node["connections"]:
            edge = tuple(sorted((node_id, neighbor_id)))
            if edge in drawn_edges:
                continue
            drawn_edges.add(edge)
            traveled = node_id in visited and neighbor_id in visited
            color = (210, 180, 90) if traveled else (90, 90, 105)
            width = 5 if traveled else 3
            pygame.draw.line(surface, color, NODES[node_id]["pos"], NODES[neighbor_id]["pos"], width)

    for node_id, node in NODES.items():
        x, y = node["pos"]
        is_current = node_id == current_node
        is_visited = node_id in visited
        base_color = (200, 90, 90) if node["type"] == "stage" else (90, 140, 200)
        if not is_visited:
            base_color = tuple(c // 2 for c in base_color)

        radius = 22 if is_current else 16
        pygame.draw.circle(surface, (10, 10, 15), (x, y), radius + 3)
        pygame.draw.circle(surface, base_color, (x, y), radius)
        pygame.draw.circle(surface, PANEL_BORDER if is_current else (230, 230, 230), (x, y), radius, 3)

        label = font.render(node["name"], True, TEXT_MAIN if is_visited else TEXT_DIM)
        surface.blit(label, (x - label.get_width() // 2, y + radius + 8))


def draw_troop_marker(surface, leader_icon, pos, bob_offset):
    x, y = pos
    y += bob_offset
    if leader_icon:
        rect = leader_icon.get_rect(center=(x, y - 30))
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


def unit_list_layout(units, frame=None):
    # Wide enough that after the ~110px frame border eats into both sides,
    # a full row (portrait + name/class + faith/mp) still has the ~460px
    # of width the original tight layout was designed for.
    width, height = 680, 240 + len(units) * 46
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(mx + 14, my + 40, width - 28, height - 54)
    row_rects = [pygame.Rect(content.x - 6, content.y + 34 + idx * 46 - 4, content.width + 12, 40) for idx in range(len(units))]
    return panel_rect, row_rects


def draw_unit_list(surface, font, units, portraits, index, frame=None):
    panel_rect, row_rects = unit_list_layout(units, frame)
    draw_panel_bg(surface, panel_rect, frame)
    content = frame_content_rect(panel_rect, frame) if frame else pygame.Rect(panel_rect.x + 14, panel_rect.y + 40, panel_rect.width - 28, panel_rect.height - 54)
    surface.blit(font.render("UNIT", True, PANEL_BORDER), (content.x, content.y))

    for idx, unit in enumerate(units):
        row_y = content.y + 34 + idx * 46
        selected = idx == index
        if selected:
            pygame.draw.rect(surface, (35, 35, 55), row_rects[idx])
        portrait = portraits.get(unit.name)
        if portrait:
            thumb = pygame.transform.smoothscale(portrait, (56, 28))
            surface.blit(thumb, (content.x, row_y))
        name_color = PANEL_BORDER if selected else TEXT_MAIN
        pointer = "->" if selected else "  "
        surface.blit(font.render(f"{pointer} {unit.name}", True, name_color), (content.x + 66, row_y))
        surface.blit(font.render(unit.char_class, True, TEXT_DIM), (content.x + 66, row_y + 18))
        stats_text = f"Faith {round(unit.faith):3}/{FAITH_CAP}   MP {unit.mp:2}/{unit.max_mp}"
        surface.blit(font.render(stats_text, True, TEAM_COLOR), (content.x + 246, row_y + 6))


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
    "mp": "Spent to cast skills that have an MP cost. Fully restored by Myrrh.",
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

    return panel_rect, equip_button, books_button, stat_hover_rects


def draw_unit_detail(surface, font, unit, portraits, frame=None):
    panel_rect, equip_button, books_button, stat_hover_rects = unit_detail_layout(frame)
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
    surface.blit(font.render(f"MP  {unit.mp:3} / {unit.max_mp}", True, (120, 170, 240)), (cx + 170, cy + 104))

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


async def main():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    required_files = ["map_layout.csv", "skills.csv", "items.csv", "equipment.csv", "characters.csv", "terrain_layout.csv", "game_settings.csv", "dialogues.csv"]
    if not all(os.path.exists(os.path.join(data_dir, filename)) for filename in required_files):
        generate_dummy_csv_files()

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Tactics Engine: World Map")
    bring_window_to_front()
    clock = pygame.time.Clock()
    font = get_font(22)
    title_font = get_font(34)

    map_background = load_image_safe("assets/world_map.jpg")
    if map_background:
        map_background = pygame.transform.smoothscale(map_background, (SCREEN_WIDTH, SCREEN_HEIGHT))

    ui_frame = load_nine_slice_frame()

    stage_manifest = load_stage_manifest()

    roster_source = stage_manifest.get(START_NODE, {}).get("characters")
    roster = load_characters_from_csv(roster_source)
    units = [Unit(char_data) for char_data in roster if char_data["team"] == "Player"]
    portraits = build_character_face_portraits(units, [])
    leader = units[0] if units else None
    leader_icon = None
    if leader and portraits.get(leader.name):
        leader_icon = pygame.transform.smoothscale(portraits[leader.name], (84, 42))

    equipment_registry = load_equipment_from_csv()
    equipment_pools = equipment_by_slot(equipment_registry)

    books_registry = load_books_from_csv()
    book_pool = sorted(books_registry.keys())

    state = STATE_MAP
    current_node = START_NODE
    visited = {START_NODE}
    transition_from = None
    transition_to = None
    transition_progress = 0.0

    menu_index = 0
    unit_index = 0
    selected_unit = None
    equip_slot_index = 0
    book_slot_index = 0
    mouse_pos = (0, 0)

    menu_button = pygame.Rect(SCREEN_WIDTH - 130, 20, 110, 34)

    async def enter_battle(node_id):
        equipment_loadout = {u.name: dict(u.equipment) for u in units}
        book_loadout = {
            u.name: {"books": dict(u.books), "turns": dict(u.book_turns), "gain": dict(u.book_gain)}
            for u in units
        }
        progress = await run_battle(stage=stage_manifest.get(node_id), equipment_loadout=equipment_loadout, book_loadout=book_loadout)
        if progress:
            for u in units:
                p = progress.get(u.name)
                if p:
                    u.books = p.get("books", u.books)
                    u.book_turns = p.get("turns", u.book_turns)
                    u.book_gain = p.get("gain", u.book_gain)
        pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Tactics Engine: World Map")

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
                elif state == STATE_MAP:
                    clicked_node = node_at_pos(event.pos)
                    if clicked_node == current_node:
                        if NODES[current_node]["type"] == "stage":
                            await enter_battle(current_node)
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
                        elif choice == "Close":
                            state = STATE_MAP
                    elif not panel_rect.collidepoint(event.pos):
                        state = STATE_MAP

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
                    _, equip_button, books_button, _ = unit_detail_layout(ui_frame)
                    if equip_button.collidepoint(event.pos):
                        state = STATE_EQUIPMENT
                        equip_slot_index = 0
                    elif books_button.collidepoint(event.pos):
                        state = STATE_BOOKS
                        book_slot_index = 0
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
                        if NODES[current_node]["type"] == "stage":
                            await enter_battle(current_node)

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
                        elif choice == "Close":
                            state = STATE_MAP

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
                transition_from = None
                transition_to = None
                state = STATE_MAP

        # --- DRAW ---
        if map_background:
            screen.blit(map_background, (0, 0))
        else:
            screen.fill((30, 34, 40))
        title = title_font.render("The Road to Rome", True, PANEL_BORDER)
        screen.blit(title, (30, 24))

        draw_path_and_nodes(screen, font, current_node, visited)

        if state == STATE_TRANSITION:
            fx, fy = NODES[transition_from]["pos"]
            tx, ty = NODES[transition_to]["pos"]
            pos = (fx + (tx - fx) * transition_progress, fy + (ty - fy) * transition_progress)
        else:
            pos = NODES[current_node]["pos"]
        draw_troop_marker(screen, leader_icon, pos, bob_offset)

        pygame.draw.rect(screen, PANEL_BG, menu_button)
        pygame.draw.rect(screen, PANEL_BORDER, menu_button, 2)
        screen.blit(font.render("[Esc] Menu", True, TEXT_MAIN), (menu_button.x + 8, menu_button.y + 8))

        if state == STATE_MAP:
            node = NODES[current_node]
            if node["type"] == "stage":
                draw_hint_bar(screen, font, f"Click/Arrows: Travel   |   Click node again (or Enter) to begin battle at {node['name']}   |   [Esc] Menu")
            else:
                draw_hint_bar(screen, font, f"Click/Arrows: Travel   |   {node['name']} (Waypoint)   |   [Esc] Menu")
        elif state == STATE_MENU:
            draw_command_menu(screen, font, MENU_OPTIONS, menu_index, "MENU", ui_frame)
        elif state == STATE_UNIT_LIST:
            draw_unit_list(screen, font, units, portraits, unit_index, ui_frame)
        elif state == STATE_UNIT_DETAIL and selected_unit:
            draw_unit_detail(screen, font, selected_unit, portraits, ui_frame)
            _, _, _, stat_hover_rects = unit_detail_layout(ui_frame)
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

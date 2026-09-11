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
)
from scripts.assets import build_character_portraits, load_image_safe, bring_window_to_front
from scripts.game_logic import Unit, main as run_battle

# --- WORLD MAP DATA ---
# Node layout (screen position, type, which nodes connect to which) lives in
# data/world_map_nodes.csv so it can be tuned without touching code. Falls
# back to this hardcoded route (a small, mostly-linear path in the spirit of
# the Super Mario World overworld) if that file is ever missing/malformed.
_FALLBACK_NODES = {
    "galilee":   {"pos": (352, 320),  "name": "Sea of Galilee", "type": "stage", "connections": ["capernaum"]},
    "capernaum": {"pos": (273, 570),  "name": "Capernaum",      "type": "town",  "connections": ["galilee", "cana"]},
    "cana":      {"pos": (609, 500),  "name": "Cana",           "type": "stage", "connections": ["capernaum", "nazareth", "samaria"]},
    "nazareth":  {"pos": (727, 258),  "name": "Nazareth",       "type": "stage", "connections": ["cana", "jericho"]},
    "samaria":   {"pos": (727, 695),  "name": "Samaria",        "type": "stage", "connections": ["cana", "jericho"]},
    "jericho":   {"pos": (969, 438),  "name": "Jericho",        "type": "town",  "connections": ["nazareth", "samaria", "bethany"]},
    "bethany":   {"pos": (1266, 563), "name": "Bethany",        "type": "stage", "connections": ["jericho", "jerusalem"]},
    "jerusalem": {"pos": (1406, 258), "name": "Jerusalem",      "type": "stage", "connections": ["bethany"]},
}
try:
    NODES, START_NODE = load_world_map_nodes()
    if not NODES:
        raise ValueError("world_map_nodes.csv produced no nodes")
except (OSError, ValueError, KeyError):
    NODES, START_NODE = _FALLBACK_NODES, "galilee"
NODE_CLICK_RADIUS = 26

STATE_MAP = "MAP"
STATE_TRANSITION = "TRANSITION"
STATE_MENU = "MENU"
STATE_UNIT_LIST = "UNIT_LIST"
STATE_UNIT_DETAIL = "UNIT_DETAIL"
STATE_EQUIPMENT = "EQUIPMENT"

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


def command_menu_layout(options):
    width, height = 220, 60 + len(options) * 30
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    option_rects = [pygame.Rect(mx + 10, my + 46 + idx * 30, width - 20, 26) for idx in range(len(options))]
    return panel_rect, option_rects


def draw_command_menu(surface, font, options, index, title):
    panel_rect, option_rects = command_menu_layout(options)
    pygame.draw.rect(surface, PANEL_BG, panel_rect)
    pygame.draw.rect(surface, PANEL_BORDER, panel_rect, 2)
    surface.blit(font.render(title, True, PANEL_BORDER), (panel_rect.x + 14, panel_rect.y + 12))
    for idx, (opt, rect) in enumerate(zip(options, option_rects)):
        color = PANEL_BORDER if idx == index else TEXT_MAIN
        pointer = " -> " if idx == index else "    "
        surface.blit(font.render(f"{pointer}{opt}", True, color), (rect.x, rect.y))


def unit_list_layout(units):
    width, height = 460, 60 + len(units) * 46
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    row_rects = [pygame.Rect(mx + 6, my + 46 + idx * 46 - 4, width - 12, 40) for idx in range(len(units))]
    return panel_rect, row_rects


def draw_unit_list(surface, font, units, portraits, index):
    panel_rect, row_rects = unit_list_layout(units)
    mx, my, width = panel_rect.x, panel_rect.y, panel_rect.width
    pygame.draw.rect(surface, PANEL_BG, panel_rect)
    pygame.draw.rect(surface, PANEL_BORDER, panel_rect, 2)
    surface.blit(font.render("UNIT", True, PANEL_BORDER), (mx + 14, my + 12))

    for idx, unit in enumerate(units):
        row_y = my + 46 + idx * 46
        selected = idx == index
        if selected:
            pygame.draw.rect(surface, (35, 35, 55), row_rects[idx])
        portrait = portraits.get(unit.name)
        if portrait:
            thumb = pygame.transform.smoothscale(portrait, (56, 28))
            surface.blit(thumb, (mx + 12, row_y))
        name_color = PANEL_BORDER if selected else TEXT_MAIN
        pointer = "->" if selected else "  "
        surface.blit(font.render(f"{pointer} {unit.name}", True, name_color), (mx + 80, row_y))
        surface.blit(font.render(unit.char_class, True, TEXT_DIM), (mx + 80, row_y + 18))
        stats_text = f"Faith {round(unit.faith):3}/{FAITH_CAP}   MP {unit.mp:2}/{unit.max_mp}"
        surface.blit(font.render(stats_text, True, TEAM_COLOR), (mx + 260, row_y + 6))


def unit_detail_layout():
    width, height = 520, 420
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    equip_button = pygame.Rect(mx + width - 140, my + height - 34, 124, 26)
    return panel_rect, equip_button


def draw_unit_detail(surface, font, unit, portraits):
    panel_rect, equip_button = unit_detail_layout()
    mx, my, width, height = panel_rect.x, panel_rect.y, panel_rect.width, panel_rect.height
    pygame.draw.rect(surface, PANEL_BG, (mx, my, width, height))
    pygame.draw.rect(surface, PANEL_BORDER, (mx, my, width, height), 2)
    pygame.draw.line(surface, PANEL_BORDER, (mx, my + 46), (mx + width, my + 46), 1)

    portrait = portraits.get(unit.name)
    if portrait:
        thumb = pygame.transform.smoothscale(portrait, (140, 70))
        surface.blit(thumb, (mx + 16, my + 60))

    surface.blit(font.render(unit.name, True, PANEL_BORDER), (mx + 16, my + 12))
    surface.blit(font.render(unit.char_class, True, TEXT_DIM), (mx + 170, my + 62))
    surface.blit(font.render(f"Faith  {round(unit.faith):3} / {FAITH_CAP}", True, (255, 215, 0)), (mx + 170, my + 84))
    surface.blit(font.render(f"MP  {unit.mp:3} / {unit.max_mp}", True, (120, 170, 240)), (mx + 170, my + 104))

    pygame.draw.line(surface, (70, 70, 85), (mx + 16, my + 150), (mx + width - 16, my + 150), 1)

    stat_rows = [
        ("Magic Attack", unit.magic_attack), ("Magic Defense", unit.magic_defense),
        ("Bravery", unit.bravery), ("Patience", unit.patience),
        ("Love", unit.love),
    ]
    col_x = [mx + 16, mx + 270]
    for idx, (label, value) in enumerate(stat_rows):
        col = idx // 3
        row = idx % 3
        y = my + 172 + row * 26
        surface.blit(font.render(f"{label:16}", True, TEXT_DIM), (col_x[col], y))
        surface.blit(font.render(f"{value}", True, TEXT_MAIN), (col_x[col] + 190, y))

    pygame.draw.line(surface, (70, 70, 85), (mx + 16, my + 288), (mx + width - 16, my + 288), 1)
    surface.blit(font.render("Skills", True, PANEL_BORDER), (mx + 16, my + 300))
    skills_text = "   ".join(unit.skills) if unit.skills else "-"
    surface.blit(font.render(skills_text, True, TEXT_MAIN), (mx + 16, my + 324))

    surface.blit(font.render("[Enter / Esc] Back", True, TEXT_DIM), (mx + 16, my + height - 28))

    pygame.draw.rect(surface, PANEL_BG, equip_button)
    pygame.draw.rect(surface, PANEL_BORDER, equip_button, 2)
    label = font.render("[E] Equip", True, PANEL_BORDER)
    surface.blit(label, label.get_rect(center=equip_button.center))


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


def equipment_screen_layout():
    width = 620
    height = 100 + len(UNIT_EQUIPMENT_SLOTS) * 36 + 70
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    row_rects = [pygame.Rect(mx + 16, my + 90 + idx * 36, width - 32, 30) for idx in range(len(UNIT_EQUIPMENT_SLOTS))]
    left_arrows = [pygame.Rect(r.right - 210, r.y, 26, r.height) for r in row_rects]
    right_arrows = [pygame.Rect(r.right - 26, r.y, 26, r.height) for r in row_rects]
    return panel_rect, row_rects, left_arrows, right_arrows


def draw_equipment_screen(surface, font, unit, portraits, slot_index, equipment_registry):
    panel_rect, row_rects, left_arrows, right_arrows = equipment_screen_layout()
    mx, my, width, height = panel_rect.x, panel_rect.y, panel_rect.width, panel_rect.height
    pygame.draw.rect(surface, PANEL_BG, panel_rect)
    pygame.draw.rect(surface, PANEL_BORDER, panel_rect, 2)
    pygame.draw.line(surface, PANEL_BORDER, (mx, my + 46), (mx + width, my + 46), 1)

    portrait = portraits.get(unit.name)
    if portrait:
        thumb = pygame.transform.smoothscale(portrait, (100, 50))
        surface.blit(thumb, (mx + 16, my + 56))
    surface.blit(font.render(f"{unit.name} - Equipment", True, PANEL_BORDER), (mx + 16, my + 12))
    surface.blit(font.render(unit.char_class, True, TEXT_DIM), (mx + 130, my + 62))

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
    desc_y = my + 90 + len(UNIT_EQUIPMENT_SLOTS) * 36 + 6
    surface.blit(font.render(description, True, TEXT_DIM), (mx + 16, desc_y))

    totals = equipped_stat_totals(unit, equipment_registry)
    totals_text = "  ".join(f"+{amount} {stat.replace('_', ' ').title()}" for stat, amount in totals.items()) or "No bonuses equipped."
    surface.blit(font.render(totals_text, True, (255, 215, 0)), (mx + 16, my + height - 50))
    surface.blit(font.render("[Left/Right] Change item   [Up/Down] Select slot   [Esc] Back", True, TEXT_DIM), (mx + 16, my + height - 26))


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
    font = pygame.font.SysFont(None, 22)
    title_font = pygame.font.SysFont(None, 34)

    map_background = load_image_safe("assets/world_map.jpg")
    if map_background:
        map_background = pygame.transform.smoothscale(map_background, (SCREEN_WIDTH, SCREEN_HEIGHT))

    stage_manifest = load_stage_manifest()

    roster_source = stage_manifest.get(START_NODE, {}).get("characters")
    roster = load_characters_from_csv(roster_source)
    units = [Unit(char_data) for char_data in roster if char_data["team"] == "Player"]
    portraits = build_character_portraits(units, [])
    leader = units[0] if units else None
    leader_icon = None
    if leader and portraits.get(leader.name):
        leader_icon = pygame.transform.smoothscale(portraits[leader.name], (84, 42))

    equipment_registry = load_equipment_from_csv()
    equipment_pools = equipment_by_slot(equipment_registry)

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

    menu_button = pygame.Rect(SCREEN_WIDTH - 130, 20, 110, 34)

    async def enter_battle(node_id):
        equipment_loadout = {u.name: dict(u.equipment) for u in units}
        await run_battle(stage=stage_manifest.get(node_id), equipment_loadout=equipment_loadout)
        pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Tactics Engine: World Map")

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        bob_offset = math.sin(pygame.time.get_ticks() / 250.0) * 4

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

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
                    panel_rect, option_rects = command_menu_layout(MENU_OPTIONS)
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
                    panel_rect, row_rects = unit_list_layout(units)
                    clicked = next((idx for idx, rect in enumerate(row_rects) if rect.collidepoint(event.pos)), None)
                    if clicked is not None:
                        unit_index = clicked
                        selected_unit = units[clicked]
                        state = STATE_UNIT_DETAIL
                    elif not panel_rect.collidepoint(event.pos):
                        state = STATE_MENU
                        menu_index = 0

                elif state == STATE_UNIT_DETAIL:
                    _, equip_button = unit_detail_layout()
                    if equip_button.collidepoint(event.pos):
                        state = STATE_EQUIPMENT
                        equip_slot_index = 0
                    else:
                        state = STATE_UNIT_LIST

                elif state == STATE_EQUIPMENT:
                    panel_rect, row_rects, left_arrows, right_arrows = equipment_screen_layout()
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
        title = title_font.render("The Road to Jerusalem", True, PANEL_BORDER)
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
            draw_command_menu(screen, font, MENU_OPTIONS, menu_index, "MENU")
        elif state == STATE_UNIT_LIST:
            draw_unit_list(screen, font, units, portraits, unit_index)
        elif state == STATE_UNIT_DETAIL and selected_unit:
            draw_unit_detail(screen, font, selected_unit, portraits)
        elif state == STATE_EQUIPMENT and selected_unit:
            draw_equipment_screen(screen, font, selected_unit, portraits, equip_slot_index, equipment_registry)

        pygame.display.flip()
        await asyncio.sleep(0)


if __name__ == "__main__":
    asyncio.run(main())
    pygame.quit()
    sys.exit()

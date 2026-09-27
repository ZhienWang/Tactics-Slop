"""Standalone map-editing tool: pick which terrain texture goes on a tile,
size the map, stack tile heights, and place more than one tile in the same
(x, y) column to build a bridge/platform floating above a gap.

Runs synchronously - unlike world_map.py/game_logic.py, this tool never
needs pygbag/web export, so there's no reason to carry asyncio into a local
dev tool.

Saved maps are written in two forms:
  - data/stages/<name>/map_layers.csv - the sparse "one row per physical
    tile" format this tool works in natively. It's the only format that can
    represent a bridge (2+ tiles sharing an (x, y)) or a hole (0 tiles at
    an (x, y)), so it's always written and is the source of truth for
    re-opening a map here.
  - data/stages/<name>/map_layout.csv + terrain_layout.csv - the legacy
    dense grids the live battle engine actually reads. These are only
    written when the map has exactly one tile per cell (no bridges, no
    holes) - the engine has no concept of multiple heights at one (x, y)
    yet, so a bridge map can be authored and saved here but isn't playable
    in battle until that support is added separately.

This tool does not touch data/stages.csv or any stage's characters.csv, so
a brand-new map isn't automatically wired into the campaign/world map -
that's a separate, deliberate step.
"""
import copy
import os
import random
import pygame

from scripts.config import SCREEN_WIDTH, SCREEN_HEIGHT, TILE_HEIGHT, CURSOR_COLOR
from scripts.data_editor import (
    DATA_DIR,
    TERRAIN_TILE_PATHS,
    WATER_TILE_PATH,
    load_stage_manifest,
    load_map_from_csv,
    load_terrain_from_csv,
    load_map_layers_csv,
    save_map_layers_csv,
    dense_grids_to_tiles,
    tiles_to_dense_grids,
    save_map_layout_csv,
    save_terrain_layout_csv,
    load_characters_from_csv,
    update_character_positions_csv,
    normalize_height,
)
from scripts.assets import load_image_safe, cache_terrain_colors, bring_window_to_front, get_font
from scripts.game_logic import iso_to_screen, draw_iso_tile, get_render_order
from scripts.controls import point_in_polygon, tile_corner_offsets, tile_top_points

PALETTE = TERRAIN_TILE_PATHS + [WATER_TILE_PATH]

PANEL_BG = (18, 18, 30)
PANEL_BORDER = CURSOR_COLOR
TEXT_MAIN = (235, 235, 235)
TEXT_DIM = (150, 150, 160)
ACCENT = (90, 160, 255)
PANEL_RADIUS = 6
SHADOW_COLOR = (0, 0, 0, 90)

DEFAULT_ROWS = 8
DEFAULT_COLS = 8
MIN_MAP_SIZE = 2
MAX_MAP_SIZE = 40
MAX_HEIGHT = 10
ADD_LAYER_GAP = 2
# Holding Shift turns every height control into this smaller step - how a
# slope tile (a 0.5, 1.5, ... height) gets authored.
SLOPE_HEIGHT_STEP = 0.5
DEFAULT_TERRAIN = "assets/grass.jpg"

TOOLS = ["paint", "add", "remove", "units"]
TOOL_LABELS = ["Paint", "Add Layer", "Remove", "Units"]
UNDO_HISTORY_LIMIT = 50
UNIT_MARKER_RADIUS = 10
TEAM_MARKER_COLORS = {"Player": (70, 140, 255), "Enemy": (220, 60, 60)}

SIDEBAR_X = SCREEN_WIDTH - 240
SIDEBAR_WIDTH = 230


def build_wood_plank_texture(width, height, seed=1):
    """Draws a vertical wood-plank panel from scratch - the game's own
    wood.png is a small isometric TILE SPRITE (a diamond with its own
    background baked in), so tiling it just produces a grid of diamonds,
    not anything that reads as wood grain. This draws actual planks with
    grain streaks and knots instead."""
    rng = random.Random(seed)
    surface = pygame.Surface((width, height))
    base = (94, 62, 38)
    surface.fill(base)

    plank_width = 46
    for plank_x in range(0, width, plank_width):
        shade = rng.randint(-10, 10)
        plank_color = tuple(max(0, min(255, c + shade)) for c in base)
        pygame.draw.rect(surface, plank_color, (plank_x, 0, plank_width, height))
        # A handful of horizontal grain streaks per plank, varied length/darkness.
        for _ in range(height // 22):
            gy = rng.randint(0, height)
            gx = plank_x + rng.randint(0, plank_width // 3)
            glen = rng.randint(plank_width // 3, plank_width - 4)
            gdark = rng.randint(18, 40)
            grain_color = tuple(max(0, c - gdark) for c in plank_color)
            pygame.draw.line(surface, grain_color, (gx, gy), (gx + glen, gy), 1)
        # One or two small knots for character.
        for _ in range(rng.randint(0, 2)):
            kx = plank_x + rng.randint(8, plank_width - 8)
            ky = rng.randint(20, height - 20)
            knot_color = tuple(max(0, c - 45) for c in plank_color)
            pygame.draw.ellipse(surface, knot_color, (kx - 5, ky - 7, 10, 14))
            pygame.draw.ellipse(surface, tuple(max(0, c - 60) for c in plank_color), (kx - 2, ky - 3, 4, 6))
        # A darker seam between planks.
        pygame.draw.line(surface, (40, 26, 15), (plank_x, 0), (plank_x, height), 2)
    return surface


def build_vignette(width, height, edge_color, center_color, steps=48):
    """A cheap radial vignette - concentric filled circles shrinking from
    edge_color at the corners to center_color in the middle - precomputed
    once at startup rather than redrawn every frame."""
    surface = pygame.Surface((width, height))
    surface.fill(edge_color)
    cx, cy = width // 2, height // 2
    max_radius = int(((width / 2) ** 2 + (height / 2) ** 2) ** 0.5)
    for step in range(steps, 0, -1):
        t = step / steps
        radius = int(max_radius * t)
        color = tuple(int(edge_color[c] + (center_color[c] - edge_color[c]) * (1 - t)) for c in range(3))
        pygame.draw.circle(surface, color, (cx, cy), radius)
    return surface


def tiles_dict_from_list(tile_list):
    """Groups a flat tile list into {(x, y): [tile, ...]}, each column kept
    sorted by height ascending - the working representation the rest of
    this module expects."""
    by_column = {}
    for tile in tile_list:
        by_column.setdefault((tile["x"], tile["y"]), []).append(tile)
    for column in by_column.values():
        column.sort(key=lambda t: t["z"])
    return by_column


def flatten_tiles(tiles):
    flat = []
    for column in tiles.values():
        flat.extend(column)
    return flat


def topmost(tiles, x, y):
    """Height of the topmost tile in a column, or 0 for an empty column
    (a hole) - used both for hit-testing (hit_test needs a scalar height
    per cell to build each tile's screen polygon) and as the "floor" a new
    bridge layer stacks above."""
    column = tiles.get((x, y))
    return column[-1]["z"] if column else 0


def topmost_grid(tiles, rows, cols):
    """Every column's topmost height as a dense [row][col] grid - the shape
    controls.tile_corner_offsets reads neighbor heights from to decide
    which way a slope tile tilts."""
    return [[topmost(tiles, x, y) for x in range(cols)] for y in range(rows)]


def height_step():
    return SLOPE_HEIGHT_STEP if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1


def hit_test(mx, my, origin_x, origin_y, tiles, rows, cols, rotation, zoom):
    """Which column the screen point (mx, my) is over, preferring whichever
    tile is drawn frontmost. get_render_order sorts back-to-front for
    painting, so walking it in reverse visits front-to-back - the first
    matching polygon is the visually correct pick. This matters here in a
    way it doesn't for controls.screen_to_map: that helper just keeps the
    *last* row-major match, which is fine for the real game's near-flat
    maps, but a tall stacked/bridge tile's polygon can shift far enough
    up-screen to overlap a neighboring cell, so row-major "last wins" often
    grabs the wrong column."""
    heights = topmost_grid(tiles, rows, cols)
    for x, y in reversed(get_render_order(cols, rows, rotation)):
        z = heights[y][x]
        sx, sy = iso_to_screen(x, y, z, origin_x, origin_y, rotation, cols, rows, zoom)
        top_points = tile_top_points(sx, sy, zoom, tile_corner_offsets(heights, x, y, rotation))
        if point_in_polygon((mx, my), top_points):
            return (x, y)
    return None


def blank_tiles(rows, cols, terrain=DEFAULT_TERRAIN):
    """A freshly-paved flat map - height 0 everywhere, one tile per cell -
    rather than starting as all holes, so a new map is immediately visible
    and paintable."""
    tiles = {}
    for y in range(rows):
        for x in range(cols):
            tiles[(x, y)] = [{"x": x, "y": y, "z": 0, "terrain": terrain}]
    return tiles


def resize_tiles(tiles, old_rows, old_cols, new_rows, new_cols, terrain=DEFAULT_TERRAIN):
    """Drops columns that fall outside the new bounds when shrinking, and
    paves new cells at height 0 when growing (consistent with blank_tiles,
    so growing the map doesn't leave a jarring void of holes)."""
    resized = {}
    for (x, y), column in tiles.items():
        if x < new_cols and y < new_rows:
            resized[(x, y)] = [dict(t) for t in column]
    for y in range(new_rows):
        for x in range(new_cols):
            if (x, y) not in resized:
                resized[(x, y)] = [{"x": x, "y": y, "z": 0, "terrain": terrain}]
    return resized


def snapshot_state(state):
    return {
        "tiles": copy.deepcopy(state["tiles"]),
        "rows": state["rows"],
        "cols": state["cols"],
        "characters": copy.deepcopy(state["characters"]),
    }


def restore_snapshot(state, snap):
    state["tiles"] = snap["tiles"]
    state["rows"] = snap["rows"]
    state["cols"] = snap["cols"]
    state["characters"] = snap["characters"]
    state["selected_character"] = None


def push_undo(state):
    """Call this right before any action that mutates tiles/rows/cols/
    characters, so that action becomes a single undo step. Starting a new
    action always clears the redo stack - redoing past a fresh edit would
    silently discard it otherwise."""
    state["undo_stack"].append(snapshot_state(state))
    if len(state["undo_stack"]) > UNDO_HISTORY_LIMIT:
        state["undo_stack"].pop(0)
    state["redo_stack"].clear()


def undo(state):
    if not state["undo_stack"]:
        return False
    state["redo_stack"].append(snapshot_state(state))
    restore_snapshot(state, state["undo_stack"].pop())
    return True


def redo(state):
    if not state["redo_stack"]:
        return False
    state["undo_stack"].append(snapshot_state(state))
    restore_snapshot(state, state["redo_stack"].pop())
    return True


def character_marker_pos(character, tiles, origin_x, origin_y, rotation, cols, rows, zoom):
    z = topmost(tiles, character["x"], character["y"])
    sx, sy = iso_to_screen(character["x"], character["y"], z, origin_x, origin_y, rotation, cols, rows, zoom)
    return (sx, sy + (TILE_HEIGHT * zoom) / 2 - 12 * zoom)


def find_character_at(characters, mx, my, tiles, origin_x, origin_y, rotation, cols, rows, zoom):
    hit_radius = UNIT_MARKER_RADIUS * zoom + 4
    for character in characters:
        cx, cy = character_marker_pos(character, tiles, origin_x, origin_y, rotation, cols, rows, zoom)
        if (mx - cx) ** 2 + (my - cy) ** 2 <= hit_radius ** 2:
            return character
    return None


def load_tiles_for_stage(stage):
    """Prefers a stage's own map_layers.csv (the richer, editor-native
    format, present if this tool already saved it once) and falls back to
    converting its legacy map_layout.csv + terrain_layout.csv. Returns
    (tiles_dict, rows, cols)."""
    stage_dir = os.path.dirname(stage["characters"])
    layers_path = os.path.join(stage_dir, "map_layers.csv")
    if os.path.exists(layers_path):
        tile_list = load_map_layers_csv(layers_path)
        rows = max((t["y"] for t in tile_list), default=-1) + 1
        cols = max((t["x"] for t in tile_list), default=-1) + 1
        rows = max(rows, DEFAULT_ROWS)
        cols = max(cols, DEFAULT_COLS)
        return tiles_dict_from_list(tile_list), rows, cols

    map_grid = load_map_from_csv(stage["map_layout"])
    terrain_grid = load_terrain_from_csv(stage["terrain_layout"])
    rows, cols = len(map_grid), (len(map_grid[0]) if map_grid else 0)
    tile_list = dense_grids_to_tiles(map_grid, terrain_grid)
    return tiles_dict_from_list(tile_list), rows, cols


def stage_dir_for_name(name):
    return os.path.join(DATA_DIR, "stages", name)


def save_tiles(state, stage_name):
    """Always writes map_layers.csv; also writes the legacy dense CSVs if
    the map is exportable that way, and - if characters were loaded from
    this same stage - writes their updated positions back to its
    characters.csv. Returns a human-readable status line."""
    target_dir = stage_dir_for_name(stage_name)
    os.makedirs(target_dir, exist_ok=True)
    flat = flatten_tiles(state["tiles"])
    save_map_layers_csv(os.path.join(target_dir, "map_layers.csv"), flat)

    characters_note = ""
    if state["characters"] and state["characters_source_stage"] == stage_name:
        positions = {c["name"]: (c["x"], c["y"]) for c in state["characters"]}
        characters_path = os.path.join(target_dir, "characters.csv")
        if os.path.exists(characters_path):
            update_character_positions_csv(characters_path, positions)
            characters_note = " Unit positions updated."

    dense = tiles_to_dense_grids(flat, state["rows"], state["cols"])
    if dense is None:
        return f"Saved '{stage_name}' (map_layers.csv only - has bridges/holes, not yet playable in battle).{characters_note}"

    map_grid, terrain_grid = dense
    save_map_layout_csv(os.path.join(target_dir, "map_layout.csv"), map_grid)
    save_terrain_layout_csv(os.path.join(target_dir, "terrain_layout.csv"), terrain_grid)
    return f"Saved '{stage_name}' (single-layer - playable in battle right now).{characters_note}"


# --- UI layout helpers (mirrors the panel_rect/option_rects pattern used
# throughout world_map.py and game_logic.py's draw_action_menu) ---

def palette_layout():
    cols = 4
    swatch = 48
    gap = 6
    rects = []
    for index, path in enumerate(PALETTE):
        col = index % cols
        row = index // cols
        x = SIDEBAR_X + col * (swatch + gap)
        y = 96 + row * (swatch + gap)
        rects.append(pygame.Rect(x, y, swatch, swatch))
    return rects


def tool_button_layout():
    # A 2x2 grid rather than one cramped row of 4 - "Add Layer" needs more
    # width than 4-across would leave it.
    width = (SIDEBAR_WIDTH - 6) // 2
    rects = []
    for index in range(4):
        col, row = index % 2, index // 2
        x = SIDEBAR_X + col * (width + 6)
        y = 286 + row * 34
        rects.append(pygame.Rect(x, y, width, 28))
    return TOOL_LABELS, rects


def height_button_layout():
    minus = pygame.Rect(SIDEBAR_X, 362, 32, 28)
    plus = pygame.Rect(SIDEBAR_X + SIDEBAR_WIDTH - 32, 362, 32, 28)
    return minus, plus


def action_button_layout():
    labels = ["New Map", "Load Stage", "Save"]
    rects = [pygame.Rect(SIDEBAR_X, 410 + i * 34, SIDEBAR_WIDTH, 28) for i in range(len(labels))]
    return labels, rects


def resize_button_layout():
    labels = ["+Row", "-Row", "+Col", "-Col"]
    width = (SIDEBAR_WIDTH - 18) // 4
    rects = []
    for index in range(4):
        x = SIDEBAR_X + index * (width + 6)
        rects.append(pygame.Rect(x, 528, width, 26))
    return labels, rects


def history_button_layout():
    width = (SIDEBAR_WIDTH - 6) // 2
    undo_rect = pygame.Rect(SIDEBAR_X, 582, width, 28)
    redo_rect = pygame.Rect(SIDEBAR_X + width + 6, 582, width, 28)
    return undo_rect, redo_rect


def stage_list_layout(stage_names):
    width, height = 360, 60 + len(stage_names) * 32
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    row_rects = [pygame.Rect(mx + 8, my + 46 + idx * 32, width - 16, 28) for idx in range(len(stage_names))]
    return panel_rect, row_rects


def draw_button(surface, rect, label, font, fill, border, text_color=TEXT_MAIN, border_width=1):
    shadow_rect = rect.move(0, 2)
    shadow = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(shadow, SHADOW_COLOR, shadow.get_rect(), border_radius=PANEL_RADIUS)
    surface.blit(shadow, shadow_rect)
    pygame.draw.rect(surface, fill, rect, border_radius=PANEL_RADIUS)
    pygame.draw.rect(surface, border, rect, border_width, border_radius=PANEL_RADIUS)
    text = font.render(label, True, text_color)
    surface.blit(text, text.get_rect(center=rect.center))


def draw_sidebar(surface, font, title_font, terrain_image_cache, sidebar_bg, state):
    panel_rect = pygame.Rect(SIDEBAR_X - 10, 0, SIDEBAR_WIDTH + 20, SCREEN_HEIGHT)
    if sidebar_bg is not None:
        surface.blit(sidebar_bg, panel_rect)
    else:
        pygame.draw.rect(surface, PANEL_BG, panel_rect)
    pygame.draw.line(surface, PANEL_BORDER, (SIDEBAR_X - 10, 0), (SIDEBAR_X - 10, SCREEN_HEIGHT), 3)

    title = title_font.render("MAP EDITOR", True, (0, 0, 0))
    surface.blit(title, (SIDEBAR_X + 2, 12))
    surface.blit(title_font.render("MAP EDITOR", True, PANEL_BORDER), (SIDEBAR_X, 10))
    stage_label = state["stage_name"] or "(unsaved)"
    surface.blit(font.render(f"{stage_label}  {state['cols']}x{state['rows']}", True, TEXT_MAIN), (SIDEBAR_X, 40))
    surface.blit(font.render("TERRAIN", True, TEXT_DIM), (SIDEBAR_X, 78))

    for path, rect in zip(PALETTE, palette_layout()):
        shadow = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(shadow, SHADOW_COLOR, shadow.get_rect(), border_radius=PANEL_RADIUS)
        surface.blit(shadow, rect.move(0, 2))
        image = terrain_image_cache.get(path)
        if image:
            surface.blit(pygame.transform.smoothscale(image, rect.size), rect)
        else:
            pygame.draw.rect(surface, (80, 80, 80), rect)
        border_color = PANEL_BORDER if path == state["brush_terrain"] else (70, 70, 80)
        pygame.draw.rect(surface, border_color, rect, 3 if path == state["brush_terrain"] else 1, border_radius=PANEL_RADIUS)

    surface.blit(font.render("TOOL", True, TEXT_DIM), (SIDEBAR_X, 266))
    labels, rects = tool_button_layout()
    for label, rect, key in zip(labels, rects, TOOLS):
        active = state["tool"] == key
        draw_button(surface, rect, label, font,
                    fill=(40, 60, 90) if active else (30, 30, 42),
                    border=PANEL_BORDER if active else (70, 70, 80),
                    border_width=2 if active else 1)

    if state["tool"] == "units":
        selected = state["selected_character"]
        units_text = f"Selected: {selected['name']}" if selected else "Click a unit, then a tile to move it."
        surface.blit(font.render(units_text, True, TEXT_MAIN), (SIDEBAR_X, 368))
    else:
        hovered_height = topmost(state["tiles"], *state["hovered"]) if state["hovered"] else None
        height_text = f"Height: {hovered_height}" if hovered_height is not None else "Height: -"
        surface.blit(font.render(height_text, True, TEXT_MAIN), (SIDEBAR_X + 40, 368))
        minus_rect, plus_rect = height_button_layout()
        for rect, label in [(minus_rect, "-"), (plus_rect, "+")]:
            draw_button(surface, rect, label, font, fill=(30, 30, 42), border=(70, 70, 80), border_width=2)

    labels, rects = action_button_layout()
    for label, rect in zip(labels, rects):
        draw_button(surface, rect, label, font, fill=(30, 30, 42), border=(70, 70, 80))

    surface.blit(font.render("RESIZE", True, TEXT_DIM), (SIDEBAR_X, 510))
    labels, rects = resize_button_layout()
    for label, rect in zip(labels, rects):
        draw_button(surface, rect, label, font, fill=(30, 30, 42), border=(70, 70, 80))

    surface.blit(font.render("HISTORY", True, TEXT_DIM), (SIDEBAR_X, 566))
    undo_rect, redo_rect = history_button_layout()
    for rect, label, available in [
        (undo_rect, f"Undo ({len(state['undo_stack'])})", bool(state["undo_stack"])),
        (redo_rect, f"Redo ({len(state['redo_stack'])})", bool(state["redo_stack"])),
    ]:
        draw_button(surface, rect, label, font, fill=(30, 30, 42),
                    border=(70, 70, 80) if available else (45, 45, 55),
                    text_color=TEXT_MAIN if available else TEXT_DIM)
        text = font.render(label, True, TEXT_MAIN if available else TEXT_DIM)
        surface.blit(text, text.get_rect(center=rect.center))


def draw_stage_picker(surface, font, stage_names):
    panel_rect, row_rects = stage_list_layout(stage_names)
    shadow = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
    pygame.draw.rect(shadow, SHADOW_COLOR, shadow.get_rect(), border_radius=PANEL_RADIUS)
    surface.blit(shadow, panel_rect.move(0, 4))
    pygame.draw.rect(surface, PANEL_BG, panel_rect, border_radius=PANEL_RADIUS)
    pygame.draw.rect(surface, PANEL_BORDER, panel_rect, 2, border_radius=PANEL_RADIUS)
    surface.blit(font.render("Load which stage? (Esc to cancel)", True, PANEL_BORDER), (panel_rect.x + 12, panel_rect.y + 12))
    for name, rect in zip(stage_names, row_rects):
        pygame.draw.rect(surface, (30, 30, 45), rect, border_radius=PANEL_RADIUS)
        text = font.render(name, True, TEXT_MAIN)
        surface.blit(text, (rect.x + 8, rect.y + 4))


def draw_text_prompt(surface, font, prompt):
    width, height = 420, 110
    mx, my = SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT // 2 - height // 2
    panel_rect = pygame.Rect(mx, my, width, height)
    shadow = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
    pygame.draw.rect(shadow, SHADOW_COLOR, shadow.get_rect(), border_radius=PANEL_RADIUS)
    surface.blit(shadow, panel_rect.move(0, 4))
    pygame.draw.rect(surface, PANEL_BG, panel_rect, border_radius=PANEL_RADIUS)
    pygame.draw.rect(surface, PANEL_BORDER, panel_rect, 2, border_radius=PANEL_RADIUS)
    surface.blit(font.render(prompt["label"], True, TEXT_MAIN), (mx + 16, my + 16))
    box = pygame.Rect(mx + 16, my + 44, width - 32, 30)
    pygame.draw.rect(surface, (30, 30, 42), box, border_radius=PANEL_RADIUS)
    pygame.draw.rect(surface, ACCENT, box, 2, border_radius=PANEL_RADIUS)
    surface.blit(font.render(prompt["text"] + "_", True, TEXT_MAIN), (box.x + 6, box.y + 6))
    surface.blit(font.render("[Enter] Confirm   [Esc] Cancel", True, TEXT_DIM), (mx + 16, my + height - 24))


def draw_status_bar(surface, font, state):
    panel = pygame.Rect(0, SCREEN_HEIGHT - 36, SIDEBAR_X - 10, 36)
    pygame.draw.rect(surface, PANEL_BG, panel)
    pygame.draw.rect(surface, PANEL_BORDER, panel, 1)
    hint = (
        f"Tool: {state['tool']}   Brush: {os.path.basename(state['brush_terrain'])}   "
        "Click: use tool   Wheel/+-: height (Shift: half step = slope)   Ctrl+Z/Y: undo/redo   WASD pan   Q/E rotate   Z/X zoom   Esc: quit"
    )
    surface.blit(font.render(hint, True, TEXT_DIM), (10, panel.y + 4))
    if state["status_message"]:
        surface.blit(font.render(state["status_message"], True, ACCENT), (10, panel.y + 20))


def apply_tool(state, x, y):
    tiles = state["tiles"]
    column = tiles.setdefault((x, y), [])
    if state["tool"] == "paint":
        if column:
            column[-1]["terrain"] = state["brush_terrain"]
        else:
            column.append({"x": x, "y": y, "z": 0, "terrain": state["brush_terrain"]})
    elif state["tool"] == "add":
        new_z = min(MAX_HEIGHT, topmost(tiles, x, y) + ADD_LAYER_GAP) if column else 0
        column.append({"x": x, "y": y, "z": new_z, "terrain": state["brush_terrain"]})
        column.sort(key=lambda t: t["z"])
    elif state["tool"] == "remove":
        if column:
            column.pop()
            if not column:
                del tiles[(x, y)]


def adjust_height(state, x, y, delta):
    column = state["tiles"].get((x, y))
    if not column:
        return
    column[-1]["z"] = normalize_height(max(0, min(MAX_HEIGHT, column[-1]["z"] + delta)))
    column.sort(key=lambda t: t["z"])


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Map Editor")
    bring_window_to_front()
    clock = pygame.time.Clock()
    font = get_font(20)
    title_font = get_font(28, bold=True)

    invalid_assets = []
    terrain_image_cache = {path: load_image_safe(path, invalid_assets) for path in PALETTE}
    terrain_color_cache = cache_terrain_colors(terrain_image_cache)

    # Precomputed once, not redrawn every frame: a hand-drawn wood-plank
    # sidebar panel and a subtle vignette behind the map canvas, rather
    # than the old flat color fills.
    sidebar_bg = build_wood_plank_texture(SIDEBAR_WIDTH + 20, SCREEN_HEIGHT)
    canvas_bg = build_vignette(SCREEN_WIDTH, SCREEN_HEIGHT, edge_color=(8, 8, 13), center_color=(32, 30, 40))

    state = {
        "tiles": blank_tiles(DEFAULT_ROWS, DEFAULT_COLS),
        "rows": DEFAULT_ROWS,
        "cols": DEFAULT_COLS,
        "stage_name": None,
        "brush_terrain": PALETTE[0],
        "tool": "paint",
        "hovered": None,
        "status_message": "New blank map. Pick a stage folder name and Save when ready.",
        "characters": [],
        "characters_source_stage": None,
        "selected_character": None,
        "undo_stack": [],
        "redo_stack": [],
    }

    origin_x, origin_y = SIDEBAR_X // 2, 140
    rotation = 2
    zoom = 1.3

    stage_manifest = load_stage_manifest()
    show_stage_picker = False
    prompt = None  # {"kind": "new_map" | "save_as", "label": str, "text": str}

    running = True
    while running:
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif prompt is not None and event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    prompt = None
                elif event.key == pygame.K_RETURN:
                    text = prompt["text"].strip()
                    if prompt["kind"] == "new_map":
                        try:
                            cols_str, rows_str = [p.strip() for p in text.split(",", 1)]
                            new_cols = max(MIN_MAP_SIZE, min(MAX_MAP_SIZE, int(cols_str)))
                            new_rows = max(MIN_MAP_SIZE, min(MAX_MAP_SIZE, int(rows_str)))
                            push_undo(state)
                            state["tiles"] = blank_tiles(new_rows, new_cols)
                            state["rows"], state["cols"] = new_rows, new_cols
                            state["stage_name"] = None
                            state["characters"] = []
                            state["characters_source_stage"] = None
                            state["selected_character"] = None
                            state["status_message"] = f"New {new_cols}x{new_rows} map. Unsaved."
                        except (ValueError, IndexError):
                            state["status_message"] = "Couldn't parse 'cols,rows' - try again."
                    elif prompt["kind"] == "save_as":
                        if text:
                            state["stage_name"] = text
                            state["status_message"] = save_tiles(state, text)
                    prompt = None
                elif event.key == pygame.K_BACKSPACE:
                    prompt["text"] = prompt["text"][:-1]
                elif event.unicode and event.unicode.isprintable():
                    prompt["text"] += event.unicode

            elif show_stage_picker and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                stage_names = sorted(stage_manifest.keys())
                panel_rect, row_rects = stage_list_layout(stage_names)
                clicked = next((i for i, r in enumerate(row_rects) if r.collidepoint(event.pos)), None)
                if clicked is not None:
                    name = stage_names[clicked]
                    tiles, rows, cols = load_tiles_for_stage(stage_manifest[name])
                    push_undo(state)
                    state["tiles"], state["rows"], state["cols"] = tiles, rows, cols
                    state["stage_name"] = name
                    try:
                        state["characters"] = load_characters_from_csv(stage_manifest[name]["characters"])
                    except (FileNotFoundError, OSError, KeyError):
                        state["characters"] = []
                    state["characters_source_stage"] = name
                    state["selected_character"] = None
                    state["status_message"] = f"Loaded '{name}' ({cols}x{rows}) with {len(state['characters'])} unit(s)."
                    show_stage_picker = False
                elif not panel_rect.collidepoint(event.pos):
                    show_stage_picker = False

            elif show_stage_picker and event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                show_stage_picker = False

            elif event.type == pygame.KEYDOWN and prompt is None and not show_stage_picker:
                # Ctrl+Z/Ctrl+Y must be checked before the plain K_z case
                # below (zoom in) - the physical key is the same, only the
                # modifier differs, and an elif chain stops at the first
                # match. getattr rather than event.mod directly: a genuine
                # SDL-originated KEYDOWN always carries .mod, but this
                # guards against anything (a test harness, a future
                # refactor) posting a synthetic event without it.
                mods = getattr(event, "mod", 0)
                if mods & pygame.KMOD_CTRL and event.key == pygame.K_z:
                    if undo(state):
                        state["status_message"] = "Undo."
                elif mods & pygame.KMOD_CTRL and event.key == pygame.K_y:
                    if redo(state):
                        state["status_message"] = "Redo."
                elif event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_w:
                    origin_y -= 30
                elif event.key == pygame.K_s:
                    origin_y += 30
                elif event.key == pygame.K_a:
                    origin_x -= 30
                elif event.key == pygame.K_d:
                    origin_x += 30
                elif event.key == pygame.K_q:
                    rotation = (rotation - 1) % 4
                elif event.key == pygame.K_e:
                    rotation = (rotation + 1) % 4
                elif event.key == pygame.K_z:
                    zoom = min(2.5, zoom + 0.1)
                elif event.key == pygame.K_x:
                    zoom = max(0.4, zoom - 0.1)
                elif event.key == pygame.K_p:
                    state["tool"] = "paint"
                    state["selected_character"] = None
                elif event.key == pygame.K_b:
                    state["tool"] = "add"
                    state["selected_character"] = None
                elif event.key == pygame.K_r:
                    state["tool"] = "remove"
                    state["selected_character"] = None
                elif event.key == pygame.K_u:
                    state["tool"] = "units"
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS) and state["hovered"]:
                    push_undo(state)
                    adjust_height(state, *state["hovered"], height_step())
                elif event.key == pygame.K_MINUS and state["hovered"]:
                    push_undo(state)
                    adjust_height(state, *state["hovered"], -height_step())

            elif event.type == pygame.MOUSEMOTION:
                # Only update on canvas motion - moving the mouse onto the
                # sidebar to click the height +/- buttons would otherwise
                # wipe out the tile you just hovered (hit_test correctly
                # finds no tile under the sidebar), so by the time the
                # click lands there'd be nothing left to adjust.
                if event.pos[0] < SIDEBAR_X - 10:
                    state["hovered"] = hit_test(event.pos[0], event.pos[1], origin_x, origin_y,
                                                 state["tiles"], state["rows"], state["cols"], rotation, zoom)

            elif event.type == pygame.MOUSEWHEEL and prompt is None and not show_stage_picker and state["hovered"]:
                # The event modern SDL/pygame actually sends for a real
                # mouse wheel - MOUSEBUTTONDOWN button 4/5 below is the
                # older compatibility convention some setups still use, so
                # both are handled to be safe, but this one is the one a
                # real scroll wheel is likely to fire.
                if event.y != 0:
                    push_undo(state)
                    adjust_height(state, *state["hovered"], height_step() if event.y > 0 else -height_step())

            elif event.type == pygame.MOUSEBUTTONDOWN and prompt is None and not show_stage_picker:
                if event.button in (4, 5) and state["hovered"]:
                    push_undo(state)
                    adjust_height(state, *state["hovered"], height_step() if event.button == 4 else -height_step())
                    continue
                if event.button != 1:
                    continue

                mx, my = event.pos
                if mx >= SIDEBAR_X - 10:
                    palette_hit = next((i for i, r in enumerate(palette_layout()) if r.collidepoint(event.pos)), None)
                    if palette_hit is not None:
                        state["brush_terrain"] = PALETTE[palette_hit]
                        continue
                    _, tool_rects = tool_button_layout()
                    tool_hit = next((i for i, r in enumerate(tool_rects) if r.collidepoint(event.pos)), None)
                    if tool_hit is not None:
                        state["tool"] = TOOLS[tool_hit]
                        state["selected_character"] = None
                        continue
                    minus_rect, plus_rect = height_button_layout()
                    if state["hovered"] and minus_rect.collidepoint(event.pos):
                        push_undo(state)
                        adjust_height(state, *state["hovered"], -height_step())
                        continue
                    if state["hovered"] and plus_rect.collidepoint(event.pos):
                        push_undo(state)
                        adjust_height(state, *state["hovered"], height_step())
                        continue
                    action_labels, action_rects = action_button_layout()
                    action_hit = next((i for i, r in enumerate(action_rects) if r.collidepoint(event.pos)), None)
                    if action_hit is not None:
                        label = action_labels[action_hit]
                        if label == "New Map":
                            prompt = {"kind": "new_map", "label": "New map size, as cols,rows (e.g. 8,8):", "text": f"{state['cols']},{state['rows']}"}
                        elif label == "Load Stage":
                            stage_manifest = load_stage_manifest()
                            show_stage_picker = True
                        elif label == "Save":
                            if state["stage_name"]:
                                state["status_message"] = save_tiles(state, state["stage_name"])
                            else:
                                prompt = {"kind": "save_as", "label": "Save as stage folder name:", "text": ""}
                        continue
                    resize_labels, resize_rects = resize_button_layout()
                    resize_hit = next((i for i, r in enumerate(resize_rects) if r.collidepoint(event.pos)), None)
                    if resize_hit is not None:
                        label = resize_labels[resize_hit]
                        new_rows, new_cols = state["rows"], state["cols"]
                        if label == "+Row":
                            new_rows = min(MAX_MAP_SIZE, state["rows"] + 1)
                        elif label == "-Row":
                            new_rows = max(MIN_MAP_SIZE, state["rows"] - 1)
                        elif label == "+Col":
                            new_cols = min(MAX_MAP_SIZE, state["cols"] + 1)
                        elif label == "-Col":
                            new_cols = max(MIN_MAP_SIZE, state["cols"] - 1)
                        push_undo(state)
                        state["tiles"] = resize_tiles(state["tiles"], state["rows"], state["cols"], new_rows, new_cols)
                        state["rows"], state["cols"] = new_rows, new_cols
                        continue
                    undo_rect, redo_rect = history_button_layout()
                    if undo_rect.collidepoint(event.pos):
                        state["status_message"] = "Undo." if undo(state) else "Nothing to undo."
                        continue
                    if redo_rect.collidepoint(event.pos):
                        state["status_message"] = "Redo." if redo(state) else "Nothing to redo."
                        continue

                if state["tool"] == "units":
                    clicked_char = find_character_at(state["characters"], mx, my, state["tiles"],
                                                      origin_x, origin_y, rotation, state["cols"], state["rows"], zoom)
                    if clicked_char is not None:
                        already_selected = state["selected_character"] is clicked_char
                        state["selected_character"] = None if already_selected else clicked_char
                    elif state["selected_character"] is not None:
                        hit = hit_test(mx, my, origin_x, origin_y, state["tiles"], state["rows"], state["cols"], rotation, zoom)
                        if hit is not None:
                            push_undo(state)
                            state["selected_character"]["x"], state["selected_character"]["y"] = hit
                else:
                    hit = hit_test(mx, my, origin_x, origin_y, state["tiles"], state["rows"], state["cols"], rotation, zoom)
                    if hit is not None:
                        push_undo(state)
                        apply_tool(state, *hit)

        # --- DRAW ---
        screen.blit(canvas_bg, (0, 0))
        heights = topmost_grid(state["tiles"], state["rows"], state["cols"])
        for x, y in get_render_order(state["cols"], state["rows"], rotation):
            column = state["tiles"].get((x, y))
            if not column:
                continue
            for tile in column:
                sx, sy = iso_to_screen(x, y, tile["z"], origin_x, origin_y, rotation, state["cols"], state["rows"], zoom)
                image = terrain_image_cache.get(tile["terrain"])
                wall_color = terrain_color_cache.get(tile["terrain"], (110, 110, 110))
                # Only the bottommost tile in a column gets a wall reaching
                # all the way down to true ground (a solid pillar, exactly
                # like the single-tile-per-cell live game). Anything
                # stacked above it is a floating platform - drawing its
                # wall proportional to its own height would make it look
                # like a solid pillar all the way to the ground, hiding the
                # gap that makes it a "bridge" rather than a hill. Pass
                # wall_height=0 for those so draw_iso_tile still gives it
                # the minimum TILE_DEPTH_BASE plank thickness, but nothing
                # more, leaving the gap visibly empty underneath.
                wall_height = tile["z"] if tile is column[0] else 0
                corner_offsets = tile_corner_offsets(heights, x, y, rotation, height=tile["z"])
                top_points = draw_iso_tile(screen, sx, sy, wall_height, wall_color, image, zoom, wall_color=wall_color, corner_offsets=corner_offsets)
                if tile is column[-1]:
                    label = font.render(str(tile["z"]), True, (20, 20, 20))
                    center = (sum(p[0] for p in top_points) / 4, sum(p[1] for p in top_points) / 4)
                    screen.blit(label, label.get_rect(center=center))
                    if state["hovered"] == (x, y):
                        pygame.draw.polygon(screen, CURSOR_COLOR, top_points, 3)

        for character in state["characters"]:
            marker_pos = character_marker_pos(character, state["tiles"], origin_x, origin_y, rotation, state["cols"], state["rows"], zoom)
            radius = UNIT_MARKER_RADIUS * zoom
            color = TEAM_MARKER_COLORS.get(character["team"], (200, 200, 200))
            selected = state["selected_character"] is character
            pygame.draw.circle(screen, (10, 10, 10), marker_pos, radius + 2)
            pygame.draw.circle(screen, color, marker_pos, radius)
            if selected:
                pygame.draw.circle(screen, CURSOR_COLOR, marker_pos, radius + 4, 2)
            initial = font.render(character["name"][0], True, (255, 255, 255))
            screen.blit(initial, initial.get_rect(center=marker_pos))

        draw_sidebar(screen, font, title_font, terrain_image_cache, sidebar_bg, state)
        draw_status_bar(screen, font, state)
        if show_stage_picker:
            draw_stage_picker(screen, font, sorted(stage_manifest.keys()))
        if prompt is not None:
            draw_text_prompt(screen, font, prompt)

        pygame.display.flip()


if __name__ == "__main__":
    main()
    pygame.quit()

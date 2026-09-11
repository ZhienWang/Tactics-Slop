"""Data-integrity tests: map/terrain generation and character stat bounds.

These don't touch the pygame event loop - they check the generator
functions in data_editor.py directly, and validate every character CSV
(the shared roster plus each stage's own roster) against sane stat ranges.
"""
import csv
import glob
import os

import pytest

from scripts.data_editor import (
    generate_terrain_csv,
    generate_map_csv,
    load_characters_from_csv,
    load_world_map_nodes,
    load_items_from_csv,
    load_equipment_from_csv,
    equipment_by_slot,
    EQUIPMENT_SLOTS,
    UNIT_EQUIPMENT_SLOTS,
    TERRAIN_THEMES,
    STAGE_THEMES,
    TERRAIN_TILE_WEIGHTS,
)
from scripts.config import FAITH_CAP

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CHARACTER_CSVS = [os.path.join(DATA_DIR, "characters.csv")] + glob.glob(
    os.path.join(DATA_DIR, "stages", "*", "characters.csv")
)


# --- generate_terrain_csv (tile-texture generation) ---

def test_generate_terrain_csv_produces_requested_dimensions():
    text = generate_terrain_csv(rows=4, cols=6, seed=1)
    rows = text.splitlines()
    assert len(rows) == 4
    assert all(len(row.split(",")) == 6 for row in rows)


def test_generate_terrain_csv_only_uses_tiles_from_the_given_theme():
    weights = TERRAIN_THEMES["coastal"]
    text = generate_terrain_csv(rows=5, cols=5, seed=3, weights=weights)
    used_tiles = {tile for row in text.splitlines() for tile in row.split(",")}
    assert used_tiles <= set(weights.keys())


def test_generate_terrain_csv_defaults_to_full_palette_without_weights():
    # A large-enough grid with the full (8-tile) palette and no theme
    # restriction should draw from more than just one theme's subset.
    text = generate_terrain_csv(rows=8, cols=8, seed=7)
    used_tiles = {tile for row in text.splitlines() for tile in row.split(",")}
    assert used_tiles <= set(TERRAIN_TILE_WEIGHTS.keys())
    assert len(used_tiles) > len(TERRAIN_THEMES["coastal"])


def test_generate_terrain_csv_avoids_same_tile_adjacency_where_possible():
    # The generator picks, per cell, whichever remaining tile has the fewest
    # same-tile neighbors - a best-effort heuristic, not a hard guarantee
    # (the shrinking tile pool can force an occasional repeat near the end).
    # So the real contract to test is "adjacency repeats are rare," not
    # "impossible."
    text = generate_terrain_csv(rows=8, cols=8, seed=5, weights=TERRAIN_THEMES["village"])
    grid = [row.split(",") for row in text.splitlines()]
    total_pairs = 0
    repeats = 0
    for y, row in enumerate(grid):
        for x, tile in enumerate(row):
            if x > 0:
                total_pairs += 1
                repeats += grid[y][x - 1] == tile
            if y > 0:
                total_pairs += 1
                repeats += grid[y - 1][x] == tile
    assert repeats / total_pairs < 0.2, f"{repeats}/{total_pairs} adjacent pairs repeat - avoidance isn't working"


# --- generate_map_csv (elevation generation) ---

def test_generate_map_csv_produces_requested_dimensions():
    text = generate_map_csv(rows=6, cols=8, seed=1)
    rows = text.splitlines()
    assert len(rows) == 6
    assert all(len(row.split(",")) == 8 for row in rows)


def test_generate_map_csv_values_stay_within_height_range():
    text = generate_map_csv(rows=10, cols=10, seed=2, max_height=3)
    for row in text.splitlines():
        for value in row.split(","):
            assert 0 <= int(value) <= 3


def test_generate_map_csv_is_deterministic_for_a_given_seed():
    a = generate_map_csv(rows=6, cols=6, seed="galilee")
    b = generate_map_csv(rows=6, cols=6, seed="galilee")
    assert a == b


def test_generate_map_csv_differs_across_seeds():
    a = generate_map_csv(rows=8, cols=8, seed="galilee")
    b = generate_map_csv(rows=8, cols=8, seed="jerusalem")
    assert a != b


# --- STAGE_THEMES coverage (the terrain-fallback bug fix) ---

def test_every_real_stage_has_a_terrain_theme():
    with open(os.path.join(DATA_DIR, "stages.csv"), newline="") as f:
        stage_ids = [row["node_id"] for row in csv.DictReader(f)]

    assert stage_ids, "expected at least one stage in stages.csv"
    for stage_id in stage_ids:
        theme = STAGE_THEMES.get(stage_id)
        assert theme is not None, f"{stage_id} has no entry in STAGE_THEMES"
        assert theme in TERRAIN_THEMES, f"{stage_id}'s theme {theme!r} isn't a real TERRAIN_THEMES key"


def test_stage_theme_matches_that_stage_actual_saved_terrain():
    # Each stage's hand-authored terrain_layout.csv should only use tiles
    # that its assigned theme also draws from - if someone changes a
    # stage's terrain art without updating STAGE_THEMES, this catches it.
    for stage_id, theme in STAGE_THEMES.items():
        terrain_path = os.path.join(DATA_DIR, "stages", stage_id, "terrain_layout.csv")
        if not os.path.exists(terrain_path):
            continue
        with open(terrain_path) as f:
            used_tiles = {tile for row in f.read().strip().splitlines() for tile in row.split(",")}
        theme_tiles = set(TERRAIN_THEMES[theme].keys())
        assert used_tiles <= theme_tiles, (
            f"{stage_id}'s saved terrain uses {used_tiles - theme_tiles}, "
            f"not in its '{theme}' theme"
        )


# --- Character stat bounds ---
# Ranges are set from the actual data (with headroom), not arbitrary
# numbers, so a real typo (an extra digit, a dropped minus sign, faith
# above the current cap) fails loudly instead of silently loading.

STAT_BOUNDS = {
    "speed": (1, 50),       # must be positive or the unit never reaches CT 100
    "mv": (0, 15),
    "jump": (0, 10),
    "mp": (0, 999),
    "magic_attack": (0, 200),
    "magic_defense": (0, 200),
    "bravery": (0, 100),
    "patience": (0, 100),
    "love": (0, 100),
}


def _iter_all_characters():
    for path in CHARACTER_CSVS:
        for char in load_characters_from_csv(path):
            yield path, char


@pytest.mark.parametrize("field,bounds", sorted(STAT_BOUNDS.items()))
def test_character_stats_are_within_bounds(field, bounds):
    low, high = bounds
    for path, char in _iter_all_characters():
        value = char[field]
        assert low <= value <= high, (
            f"{char['name']} in {path} has {field}={value}, expected [{low}, {high}]"
        )


def test_character_faith_is_within_the_configured_faith_cap():
    for path, char in _iter_all_characters():
        faith = char["faith"]
        assert 0 <= faith <= FAITH_CAP, (
            f"{char['name']} in {path} has faith={faith}, expected [0, {FAITH_CAP}]"
        )


def test_character_starting_positions_fit_within_their_stage_map():
    for stage_dir in sorted(glob.glob(os.path.join(DATA_DIR, "stages", "*"))):
        map_path = os.path.join(stage_dir, "map_layout.csv")
        chars_path = os.path.join(stage_dir, "characters.csv")
        if not (os.path.exists(map_path) and os.path.exists(chars_path)):
            continue
        with open(map_path) as f:
            map_rows = [line for line in f.read().strip().splitlines() if line]
        map_cols = len(map_rows[0].split(","))
        map_rows_count = len(map_rows)

        for char in load_characters_from_csv(chars_path):
            x, y = char["x"], char["y"]
            assert 0 <= x < map_cols, f"{char['name']} in {chars_path} has x={x}, map width is {map_cols}"
            assert 0 <= y < map_rows_count, f"{char['name']} in {chars_path} has y={y}, map height is {map_rows_count}"


def test_no_two_characters_share_a_starting_tile_on_the_same_stage():
    for path in CHARACTER_CSVS:
        seen = {}
        for char in load_characters_from_csv(path):
            pos = (char["x"], char["y"])
            assert pos not in seen, (
                f"{char['name']} and {seen.get(pos)} both start at {pos} in {path}"
            )
            seen[pos] = char["name"]


# --- World map node layout (data/world_map_nodes.csv) ---

def test_world_map_nodes_load_with_a_valid_start_node():
    nodes, start_node = load_world_map_nodes()

    assert nodes, "expected at least one node"
    assert start_node in nodes, f"start node {start_node!r} isn't a node in the file"


def test_world_map_every_connection_points_to_a_real_node():
    nodes, _ = load_world_map_nodes()

    for node_id, node in nodes.items():
        for target in node["connections"]:
            assert target in nodes, f"{node_id} connects to unknown node {target!r}"


def test_world_map_connections_are_symmetric():
    # The travel UI lets you go both ways along a drawn path, so a one-way
    # connection would be a dead end you can walk into but never leave.
    nodes, _ = load_world_map_nodes()

    for node_id, node in nodes.items():
        for target in node["connections"]:
            assert node_id in nodes[target]["connections"], (
                f"{node_id} -> {target} isn't reciprocated ({target} doesn't list {node_id})"
            )


def test_world_map_node_positions_fit_on_screen():
    from scripts.config import SCREEN_WIDTH, SCREEN_HEIGHT

    nodes, _ = load_world_map_nodes()
    for node_id, node in nodes.items():
        x, y = node["pos"]
        assert 0 <= x <= SCREEN_WIDTH, f"{node_id} has x={x}, outside [0, {SCREEN_WIDTH}]"
        assert 0 <= y <= SCREEN_HEIGHT, f"{node_id} has y={y}, outside [0, {SCREEN_HEIGHT}]"


# --- items.csv (consumable item catalog) ---

EXPECTED_ITEMS = {"Healing Salve", "Ankh", "Myrrh", "Frankincense", "Mustard Seed"}
VALID_ITEM_EFFECTS = {"cure_status", "revive", "restore_mp", "buff_magic_attack", "faith_boost"}
VALID_TARGET_SCOPES = {"ally", "dead_ally"}


def test_items_csv_contains_the_expected_bible_items():
    items = load_items_from_csv()
    assert EXPECTED_ITEMS.issubset(items.keys())


def test_items_csv_uses_known_effects_and_target_scopes():
    items = load_items_from_csv()
    for name, data in items.items():
        assert data["effect"] in VALID_ITEM_EFFECTS, f"{name} has an unrecognized effect: {data['effect']}"
        assert data["target_scope"] in VALID_TARGET_SCOPES, f"{name} has an unrecognized target_scope: {data['target_scope']}"
        assert data["range"] >= 1, f"{name} has a non-positive range"
        assert data["uses"] >= 1, f"{name} starts with zero stock"


def test_ankh_revive_rate_stays_within_a_sane_fraction_of_the_users_faith():
    items = load_items_from_csv()
    ankh = items["Ankh"]
    assert ankh["effect"] == "revive"
    assert 0 < ankh["amount"] <= 1  # a fraction of the reviver's own Faith, never more than all of it


# --- equipment.csv (pregenerated gear catalog for the world map's Equipment screen) ---

VALID_EQUIPMENT_STATS = {
    "magic_attack", "magic_defense", "faith", "bravery", "patience", "love", "speed", "mv", "jump",
}


def unit_slot_category(slot_key):
    return "ring" if slot_key.startswith("ring_") else slot_key


def test_equipment_csv_covers_every_unit_slot_category():
    equipment = load_equipment_from_csv()
    grouped = equipment_by_slot(equipment)
    slot_categories = {unit_slot_category(slot) for slot in UNIT_EQUIPMENT_SLOTS}
    for category in slot_categories:
        assert category in EQUIPMENT_SLOTS
        assert len(grouped[category]) >= 1, f"no items exist for slot category {category!r}"


def test_equipment_items_only_use_known_stats_and_positive_amounts():
    equipment = load_equipment_from_csv()
    for name, data in equipment.items():
        assert data["slot"] in EQUIPMENT_SLOTS, f"{name} has an unrecognized slot: {data['slot']}"
        assert 1 <= len(data["stats"]) <= 2, f"{name} should grant 1-2 stat bonuses, has {len(data['stats'])}"
        for stat, amount in data["stats"].items():
            assert stat in VALID_EQUIPMENT_STATS, f"{name} grants an unrecognized stat: {stat}"
            assert amount > 0, f"{name}'s bonus to {stat} isn't positive"


def test_ring_slots_share_a_single_catalog_category():
    equipment = load_equipment_from_csv()
    grouped = equipment_by_slot(equipment)
    assert grouped["ring"], "the shared 'ring' category should have items for both ring slots to draw from"

import glob
import os

import pytest

from scripts import game_logic
from scripts.data_editor import (
    DATA_DIR,
    load_characters_from_csv,
    load_map_from_csv,
    load_props_from_csv,
    load_terrain_from_csv,
    is_water_tile,
)


def make_unit(name, x, y, mv=3, jump=1):
    return game_logic.Unit({
        "name": name, "team": "Player", "class": "Apostle", "x": x, "y": y,
        "speed": 10, "mv": mv, "jump": jump, "mp": 0, "skills": [],
        "color": (255, 255, 255), "portrait_path": "",
    })


@pytest.fixture
def flat_map():
    """A 5x5 map at height 0 with no props, restored afterwards - these are
    module-level globals the battle fills in when a stage loads."""
    game_logic.MAP_DATA = [[0] * 5 for _ in range(5)]
    game_logic.MAP_ROWS = game_logic.MAP_COLS = 5
    game_logic.TERRAIN_LAYOUT = []
    game_logic.PROP_TILES = set()
    yield
    game_logic.PROP_TILES = set()


def test_props_csv_parses_tile_and_height(tmp_path):
    path = tmp_path / "props.csv"
    path.write_text("x,y,prop,height\n3,4,tree,3\n")

    assert load_props_from_csv(path) == [{"x": 3, "y": 4, "prop": "tree", "height": 3}]


def test_a_stage_without_props_just_has_none(tmp_path):
    assert load_props_from_csv(tmp_path / "props.csv") == []


def test_a_tree_blocks_movement_onto_its_tile(flat_map):
    unit = make_unit("Paul", 2, 2)

    assert (2, 3) in game_logic.get_valid_moves_a_star(unit, [unit])

    game_logic.PROP_TILES = {(2, 3)}

    assert (2, 3) not in game_logic.get_valid_moves_a_star(unit, [unit])


def test_a_tree_blocks_the_path_through_it_not_just_the_tile(flat_map):
    # mv 1 leaves only the one route north, so blocking it strands the tile beyond.
    unit = make_unit("Paul", 2, 2, mv=2)
    game_logic.PROP_TILES = {(2, 3)}

    assert (2, 4) not in game_logic.get_valid_moves_a_star(unit, [unit])


def test_the_ai_never_steps_into_a_tree(flat_map):
    mover = make_unit("Legionnaire", 2, 2)
    mover.team = "Enemy"
    target = make_unit("Paul", 2, 4)
    game_logic.PROP_TILES = {(2, 3)}

    assert game_logic.get_ai_move_destination(mover, [mover, target]) != (2, 3)


def test_a_shove_cannot_push_a_unit_into_a_tree(flat_map):
    caster = make_unit("Legionnaire", 2, 1)
    target = make_unit("Paul", 2, 2)
    game_logic.PROP_TILES = {(2, 3)}

    game_logic.push_unit_away(caster, target, [caster, target], tiles=2)

    assert (target.x, target.y) == (2, 2)


# A tree under 3 height units reads as a shrub; a boulder can be knee-high.
MIN_PROP_HEIGHT = {"tree": 3, "boulder": 1, "house": 2, "well": 1, "ranch": 2}
STAGE_PROP_FILES = glob.glob(os.path.join(DATA_DIR, "stages", "*", "props.csv"))


@pytest.mark.parametrize("path", STAGE_PROP_FILES)
def test_stage_props_stand_on_solid_ground_nobody_starts_on(path):
    stage_dir = os.path.dirname(path)
    heights = load_map_from_csv(os.path.join(stage_dir, "map_layout.csv"))
    terrain = load_terrain_from_csv(os.path.join(stage_dir, "terrain_layout.csv"))
    starts = {(c["x"], c["y"]) for c in load_characters_from_csv(os.path.join(stage_dir, "characters.csv"))}

    for prop in load_props_from_csv(path):
        x, y = prop["x"], prop["y"]
        assert 0 <= y < len(heights) and 0 <= x < len(heights[y]), f"{prop} is off {stage_dir}'s map"
        assert (x, y) not in starts, f"{prop} in {stage_dir} sits on a unit's starting tile"
        assert not is_water_tile(terrain[y][x]), f"{prop} in {stage_dir} is standing in water"
        assert prop["prop"] in game_logic.PROP_ART, f"{prop} in {stage_dir} has no art to draw it with"
        assert prop["height"] >= MIN_PROP_HEIGHT[prop["prop"]], f"{prop} in {stage_dir} is too short for a {prop['prop']}"


# --- Map lighting ---

def test_lighting_is_deterministic_per_map():
    from scripts.game_logic import compute_tile_lighting
    layout = [[0, 1, 0], [0, 0, 2], [1, 0, 0]]
    assert compute_tile_lighting(layout) == compute_tile_lighting(layout)


def test_taller_neighbor_on_the_sun_side_casts_shadow():
    import scripts.game_logic as game_logic
    flat = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    walled = [[0, 0, 0], [0, 0, 3], [0, 0, 0]]
    # (2, 1) is the sunward (+x) neighbor of (1, 1). Compare without the
    # random sun-patches, which differ between the two layouts.
    original = game_logic.random.Random
    try:
        game_logic.random.Random = lambda seed: original(0)
        assert game_logic.compute_tile_lighting(walled)[(1, 1)] < game_logic.compute_tile_lighting(flat)[(1, 1)]
    finally:
        game_logic.random.Random = original


def test_prop_casts_shadow_on_its_neighbor():
    import scripts.game_logic as game_logic
    flat = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    tree = {(2, 1): {"x": 2, "y": 1, "prop": "tree", "height": 3}}
    assert game_logic.compute_tile_lighting(flat, tree)[(1, 1)] < game_logic.compute_tile_lighting(flat)[(1, 1)]


def test_lighting_stays_within_bounds():
    import scripts.game_logic as game_logic
    layout = [[z % 4 for z in range(row, row + 8)] for row in range(8)]
    for light in game_logic.compute_tile_lighting(layout).values():
        assert game_logic.LIGHT_MIN <= light <= game_logic.LIGHT_MAX


# --- destroyable props ---

def stage_props(props):
    game_logic.MAP_PROPS = [dict(p, hp=game_logic.PROP_HP[p["prop"]], max_hp=game_logic.PROP_HP[p["prop"]]) for p in props]
    game_logic.PROP_TILES = {(p["x"], p["y"]) for p in props}
    game_logic.RUBBLE_TILES = set()


def test_every_prop_kind_has_hp_art_and_a_shadow():
    for kind in game_logic.PROP_ART:
        assert game_logic.PROP_HP[kind] >= 1
        assert kind in game_logic.PROP_SHADOW


def test_a_house_takes_three_hits_then_falls_and_frees_its_tile(flat_map):
    stage_props([{"x": 2, "y": 3, "prop": "house", "height": 2}])
    hitter = make_unit("Paul", 2, 2)
    version = game_logic.PROPS_VERSION
    assert "2 left" in game_logic.strike_prop(hitter, 2, 3)
    assert "1 left" in game_logic.strike_prop(hitter, 2, 3)
    assert (2, 3) in game_logic.PROP_TILES
    assert "brings down" in game_logic.strike_prop(hitter, 2, 3)
    assert (2, 3) not in game_logic.PROP_TILES
    assert (2, 3) in game_logic.RUBBLE_TILES
    assert game_logic.prop_at(2, 3) is None
    assert game_logic.PROPS_VERSION > version
    assert (2, 3) in game_logic.get_valid_moves_a_star(hitter, [hitter])


def test_a_ranch_fence_falls_to_one_hit(flat_map):
    stage_props([{"x": 1, "y": 1, "prop": "ranch", "height": 2}])
    game_logic.strike_prop(make_unit("Paul", 1, 2), 1, 1)
    assert not game_logic.MAP_PROPS


def test_striking_an_empty_tile_does_nothing(flat_map):
    stage_props([])
    assert game_logic.strike_prop(make_unit("Paul", 1, 2), 1, 1) is None


def test_reset_props_restores_a_stage_to_full_strength(tmp_path):
    path = tmp_path / "props.csv"
    path.write_text("x,y,prop,height,style\n1,1,house,2,flat\n2,2,well,1.5,\n")
    game_logic.reset_props(str(path))
    game_logic.strike_prop(make_unit("Paul", 1, 2), 1, 1)
    game_logic.reset_props(str(path))
    house = game_logic.prop_at(1, 1)
    assert house["hp"] == house["max_hp"] == 3 and house["style"] == "flat"
    assert "style" not in game_logic.prop_at(2, 2)
    game_logic.reset_props(None)
    game_logic.PROP_TILES = set()


# --- houses standing together merge into bigger houses ---

def houses(tiles, style="tiled", height=2.5):
    return {t: {"x": t[0], "y": t[1], "prop": "house", "height": height, "style": style} for t in tiles}


def square(x0, y0, size):
    return [(x0 + i, y0 + j) for j in range(size) for i in range(size)]


FLAT_6 = [[0] * 6 for _ in range(6)]


def test_a_square_of_houses_merges_into_one_block_largest_first():
    blocks = game_logic.house_blocks(houses(square(0, 0, 3)), FLAT_6)
    assert {b["size"] for b in blocks.values()} == {3}
    assert len({id(b) for b in blocks.values()}) == 1


def test_a_two_by_four_row_of_houses_makes_two_blocks():
    blocks = game_logic.house_blocks(houses(square(0, 0, 2) + square(0, 2, 2)), FLAT_6)
    assert len({id(b) for b in blocks.values()}) == 2


def test_houses_only_merge_on_level_ground():
    sloped = [row[:] for row in FLAT_6]
    sloped[1][1] = 0.5
    assert not game_logic.house_blocks(houses(square(0, 0, 2)), sloped)


def test_knocking_down_one_house_of_a_block_splits_it_back_up():
    props = houses(square(0, 0, 2))
    del props[(1, 1)]
    assert not game_logic.house_blocks(props, FLAT_6)


def test_every_strip_of_a_merged_house_is_drawn_by_one_of_its_tiles():
    pygame = pytest.importorskip("pygame")
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    for size in (2, 3, 4):
        block = game_logic.house_blocks(houses(square(0, 0, size)), [[0] * 6 for _ in range(6)])[(0, 0)]
        screen = {t: game_logic.iso_to_screen(t[0], t[1], 0, 400, 100, 0, 6, 6, 1.0) for t in block["tiles"]}
        rank = {t: i for i, t in enumerate(game_logic.get_render_order(6, 6, 0))}
        plan = game_logic.plan_house_block(block, screen, rank, 1.0)
        covered = sum(area.width for areas in plan["strips"].values() for area in areas)
        assert covered == plan["sprite"].get_width()
        assert set(plan["strips"]) <= set(block["tiles"])

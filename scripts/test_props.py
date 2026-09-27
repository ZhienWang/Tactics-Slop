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
MIN_PROP_HEIGHT = {"tree": 3, "boulder": 1}
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

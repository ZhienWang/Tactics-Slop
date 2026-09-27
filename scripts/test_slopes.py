import pytest

from scripts.controls import (
    screen_to_map,
    slope_uphill_direction,
    tile_corner_offsets,
    tile_top_points,
)
from scripts.data_editor import (
    load_map_from_csv,
    load_map_layers_csv,
    normalize_height,
    save_map_layout_csv,
)
from scripts.game_logic import iso_to_screen


def test_normalize_height_keeps_whole_heights_as_ints():
    assert normalize_height("2") == 2
    assert isinstance(normalize_height("2"), int)
    assert isinstance(normalize_height(1.0), int)


def test_normalize_height_snaps_to_the_nearest_half_step():
    assert normalize_height("0.5") == 0.5
    assert normalize_height("1.4") == 1.5
    assert normalize_height(0.9) == 1


def test_half_heights_survive_a_map_layout_csv_round_trip(tmp_path):
    path = tmp_path / "map_layout.csv"
    grid = [[0, 0.5, 1], [1, 1.5, 2]]

    save_map_layout_csv(path, grid)

    assert path.read_text().splitlines() == ["0,0.5,1", "1,1.5,2"]
    assert load_map_from_csv(path) == grid


def test_map_layers_csv_accepts_half_heights(tmp_path):
    path = tmp_path / "map_layers.csv"
    path.write_text("x,y,z,terrain\n0,0,0.5,assets/grass.jpg\n")

    assert load_map_layers_csv(path)[0]["z"] == 0.5


def test_slope_rises_toward_its_higher_neighbor():
    assert slope_uphill_direction([[0, 0.5, 1]], 1, 0) == (1, 0)
    assert slope_uphill_direction([[1, 0.5, 0]], 1, 0) == (-1, 0)
    assert slope_uphill_direction([[0], [0.5], [1]], 0, 1) == (0, 1)


def test_slope_at_the_map_edge_still_rises_toward_its_one_neighbor():
    assert slope_uphill_direction([[0.5, 1]], 0, 0) == (1, 0)


def test_whole_heights_and_lone_half_steps_are_not_slopes():
    assert slope_uphill_direction([[0, 1, 2]], 1, 0) is None
    assert slope_uphill_direction([[0, 0.5, 0]], 1, 0) is None
    assert tile_corner_offsets([[0, 0.5, 0]], 1, 0) == (0, 0, 0, 0)


def test_slope_never_rises_toward_a_neighbor_only_level_with_it():
    # The second 0.5 has nothing taller beside it, so it stays a flat
    # half-step rather than tilting up into the first slope's low edge.
    ramp = [[1, 0.5, 0.5, 0]]
    assert slope_uphill_direction(ramp, 1, 0) == (-1, 0)
    assert slope_uphill_direction(ramp, 2, 0) is None


def test_half_step_in_a_valley_stays_flat():
    assert slope_uphill_direction([[1, 0.5, 1]], 1, 0) is None


def test_slope_corner_offsets_turn_with_the_camera():
    ramp = [[0, 0.5, 1]]
    # rotation 0: uphill is +x, i.e. the right/bottom on-screen corners.
    assert tile_corner_offsets(ramp, 1, 0, rotation=0) == (-0.5, 0.5, 0.5, -0.5)
    # rotation 2 views the map from the opposite side, so the tilt flips.
    assert tile_corner_offsets(ramp, 1, 0, rotation=2) == (0.5, -0.5, -0.5, 0.5)


def _screen_corners(map_data, x, y, rotation):
    rows, cols = len(map_data), len(map_data[0])
    sx, sy = iso_to_screen(x, y, map_data[y][x], 0, 0, rotation, cols, rows)
    points = tile_top_points(sx, sy, 1.0, tile_corner_offsets(map_data, x, y, rotation))
    return {(round(px, 6), round(py, 6)) for px, py in points}


@pytest.mark.parametrize("rotation", [0, 1, 2, 3])
def test_slope_edges_meet_both_neighbors_without_a_seam(rotation):
    ramp = [[0, 0.5, 1]]
    slope = _screen_corners(ramp, 1, 0, rotation)

    assert len(slope & _screen_corners(ramp, 0, 0, rotation)) == 2
    assert len(slope & _screen_corners(ramp, 2, 0, rotation)) == 2


def test_clicking_a_slopes_lowered_corner_selects_the_slope():
    # Just inside the slope's dipped left corner - outside where a flat
    # 0.5-height diamond would be, so this only hits with slope geometry.
    assert screen_to_map(-26, 14, 0, 0, [[0.5, 1]]) == (0, 0)

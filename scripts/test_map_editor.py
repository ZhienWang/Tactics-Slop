from scripts import map_editor as ed
from scripts.data_editor import load_props_from_csv
from scripts.roster import load_party_slots, save_party_slots


def blank_state():
    return {"tiles": ed.blank_tiles(4, 4), "props": {}, "party_slots": [], "characters": [], "prop_brush": 0}


def brush(kind, style=""):
    return next(i for i, (_, k, _, s) in enumerate(ed.PROP_PALETTE) if k == kind and s == style)


def test_props_round_trip_through_props_csv(tmp_path):
    state = blank_state()
    state["prop_brush"] = brush("house")
    assert ed.place_prop(state, 1, 1) is None
    state["prop_brush"] = brush("well")
    assert ed.place_prop(state, 2, 3) is None
    ed.save_props_csv(tmp_path / "props.csv", state["props"])
    loaded = {(p["x"], p["y"]): p for p in load_props_from_csv(tmp_path / "props.csv")}
    assert loaded[(1, 1)] == {"x": 1, "y": 1, "prop": "house", "height": 3}
    assert loaded[(2, 3)] == {"x": 2, "y": 3, "prop": "well", "height": 1.5}


def test_the_eraser_removes_a_prop():
    state = blank_state()
    ed.place_prop(state, 0, 0)
    state["prop_brush"] = next(i for i, entry in enumerate(ed.PROP_PALETTE) if entry[1] is None)
    ed.place_prop(state, 0, 0)
    assert not state["props"]


def test_props_stay_out_of_the_water_and_off_start_tiles():
    state = blank_state()
    state["tiles"][(0, 0)][-1]["terrain"] = ed.WATER_TILE_PATH
    assert ed.place_prop(state, 0, 0)
    state["party_slots"] = [(1, 0)]
    assert ed.place_prop(state, 1, 0)
    state["characters"] = [{"name": "Legionnaire", "team": "Enemy", "x": 2, "y": 0}]
    assert ed.place_prop(state, 2, 0)
    assert not state["props"]


def test_party_tiles_toggle_in_order_and_only_on_open_dry_ground(tmp_path):
    state = blank_state()
    ed.toggle_party_slot(state, 0, 0)
    ed.toggle_party_slot(state, 1, 0)
    assert state["party_slots"] == [(0, 0), (1, 0)]
    ed.toggle_party_slot(state, 0, 0)
    assert state["party_slots"] == [(1, 0)]
    ed.place_prop(state, 3, 3)
    ed.toggle_party_slot(state, 3, 3)
    assert (3, 3) not in state["party_slots"]
    save_party_slots(tmp_path, state["party_slots"])
    assert load_party_slots(tmp_path) == [(1, 0)]

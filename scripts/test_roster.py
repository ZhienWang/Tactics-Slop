import os

import pytest

from scripts import game_logic, story
from scripts.data_editor import (
    DATA_DIR,
    is_water_tile,
    load_characters_from_csv,
    load_map_from_csv,
    load_props_from_csv,
    load_stage_manifest,
    load_terrain_from_csv,
)
from scripts.roster import (
    LEADER,
    START,
    choose_party,
    deploy_party,
    load_party_slots,
    load_roster,
    recruited_after,
    recruits_for,
    starting_members,
)

ROSTER = load_roster()
NAMES = [c["name"] for c in ROSTER]
STAGES = load_stage_manifest()


def test_the_roster_has_everyone_once_with_paul_first():
    assert NAMES[0] == LEADER
    assert len(NAMES) == len(set(NAMES))
    assert all(c["team"] == "Player" for c in ROSTER)


def test_only_paul_starts_and_everyone_else_joins_after_a_real_scene():
    scenes = story.load_story()
    assert starting_members(ROSTER) == [LEADER]
    for c in ROSTER:
        assert c["joins"] == START or c["joins"] in scenes, f"{c['name']} joins after unknown scene {c['joins']!r}"
        assert c["bio"], f"{c['name']} has no bio"


def test_the_company_has_men_women_and_a_donkey():
    classes = {c["name"]: c["class"] for c in ROSTER}
    assert classes["Barley"] == "Donkey"
    assert {"Rhoda", "Lois", "Eunice", "Lydia", "Phoebe", "Priscilla"} <= set(NAMES)
    assert {"Ananias", "Cornelius", "Apollos", "Eutychus", "Jailer"} <= set(NAMES)


def test_every_roster_member_has_a_token_and_known_skills():
    skills = game_logic.load_skills_from_csv()
    root = os.path.dirname(DATA_DIR)
    for c in ROSTER:
        assert os.path.exists(os.path.join(root, c["portrait_path"])), c["name"]
        assert set(c["skills"]) <= set(skills), c["name"]


def test_recruits_join_after_their_scene():
    assert "Barley" in recruits_for("lystra_intro", ROSTER)
    assert recruited_after([], ROSTER) == [LEADER]
    assert set(recruited_after(["jerusalem_intro"], ROSTER)) == {"Paul", "Barnabas", "Peter"}


@pytest.mark.parametrize("node", list(STAGES))
def test_stage_sheets_hold_only_the_enemy_and_npcs(node):
    cast = load_characters_from_csv(STAGES[node]["characters"])
    for c in cast:
        assert not (c["team"] == "Player" and c["name"] in NAMES), f"{node} still lists {c['name']} of the company"


@pytest.mark.parametrize("node", list(STAGES))
def test_every_stage_has_open_dry_start_tiles_for_the_party(node):
    stage = STAGES[node]
    folder = os.path.dirname(stage["characters"])
    slots = load_party_slots(folder)
    assert slots, f"{node} has no party_start.csv"
    assert len(slots) == len(set(slots))
    map_data = load_map_from_csv(stage["map_layout"])
    terrain = load_terrain_from_csv(stage["terrain_layout"])
    taken = {(c["x"], c["y"]) for c in load_characters_from_csv(stage["characters"])}
    props = {(p["x"], p["y"]) for p in load_props_from_csv(os.path.join(folder, "props.csv"))}
    for x, y in slots:
        assert 0 <= y < len(map_data) and 0 <= x < len(map_data[0]), (node, x, y)
        assert (x, y) not in taken | props, (node, x, y)
        assert not is_water_tile(terrain[y][x]), (node, x, y)


def test_the_party_is_the_named_members_in_roster_order_leader_first():
    party = choose_party(ROSTER, {"Barley", "Lydia", "Paul"}, 5)
    assert [c["name"] for c in party] == ["Paul", "Barley", "Lydia"]
    assert [c["name"] for c in choose_party(ROSTER, None, 2)] == NAMES[:2]


def test_a_blocked_start_tile_falls_back_to_the_nearest_free_one():
    flat = [[0] * 4 for _ in range(4)]
    placed = deploy_party(ROSTER[:2], [(0, 0), (1, 0)], flat, {(1, 0)}, {"mount": "horse"})
    assert [(c["x"], c["y"]) for c in placed][0] == (0, 0)
    assert (placed[1]["x"], placed[1]["y"]) not in {(0, 0), (1, 0)}
    assert all(c["mount"] == "horse" for c in placed)

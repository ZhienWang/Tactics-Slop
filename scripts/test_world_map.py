"""Tests for the world map's Equipment screen logic (cycling items in and
out of a slot, and summing the resulting stat bonuses). These are pure
functions - no pygame event loop involved.
"""
from scripts import world_map
from scripts.game_logic import Unit


def make_unit(name):
    return Unit({
        "name": name,
        "team": "Player",
        "class": "Apostle",
        "x": 0,
        "y": 0,
        "speed": 10,
        "mv": 3,
        "jump": 1,
        "faith": 100,
        "mp": 10,
        "skills": [],
        "color": (255, 255, 255),
        "portrait_path": "",
    })


EQUIPMENT_POOLS = {
    "helmet": ["Bronze Helm", "Helmet of Salvation"],
    "ring": ["Copper Ring", "Silver Ring"],
}
EQUIPMENT_REGISTRY = {
    "Bronze Helm": {"slot": "helmet", "stats": {"magic_defense": 8}, "description": "A soldier's helm."},
    "Helmet of Salvation": {"slot": "helmet", "stats": {"faith": 15, "magic_defense": 5}, "description": "Ephesians 6:17."},
    "Copper Ring": {"slot": "ring", "stats": {"bravery": 3}, "description": "A humble band."},
    "Silver Ring": {"slot": "ring", "stats": {"magic_attack": 5}, "description": "A polished band."},
}


def test_cycle_equipment_from_empty_moves_to_first_item():
    unit = make_unit("Peter")
    world_map.cycle_equipment(unit, "helmet", 1, EQUIPMENT_POOLS)
    assert unit.equipment["helmet"] == "Bronze Helm"


def test_cycle_equipment_wraps_past_the_end_back_to_empty():
    unit = make_unit("Peter")
    unit.equipment["helmet"] = "Helmet of Salvation"  # last item in the pool
    world_map.cycle_equipment(unit, "helmet", 1, EQUIPMENT_POOLS)
    assert unit.equipment["helmet"] is None


def test_cycle_equipment_backward_from_empty_wraps_to_last_item():
    unit = make_unit("Peter")
    world_map.cycle_equipment(unit, "helmet", -1, EQUIPMENT_POOLS)
    assert unit.equipment["helmet"] == "Helmet of Salvation"


def test_cycle_equipment_only_touches_the_given_slot():
    unit = make_unit("Peter")
    unit.equipment["ring_1"] = "Copper Ring"
    world_map.cycle_equipment(unit, "ring_2", 1, EQUIPMENT_POOLS)
    assert unit.equipment["ring_1"] == "Copper Ring"  # untouched
    assert unit.equipment["ring_2"] == "Copper Ring"  # ring_1 and ring_2 both draw from the "ring" pool


def test_equipped_stat_totals_sums_bonuses_across_slots():
    unit = make_unit("Peter")
    unit.equipment["helmet"] = "Helmet of Salvation"
    unit.equipment["ring_1"] = "Silver Ring"

    totals = world_map.equipped_stat_totals(unit, EQUIPMENT_REGISTRY)

    assert totals == {"faith": 15, "magic_defense": 5, "magic_attack": 5}


def test_equipped_stat_totals_empty_when_nothing_equipped():
    unit = make_unit("Peter")
    assert world_map.equipped_stat_totals(unit, EQUIPMENT_REGISTRY) == {}


def test_slot_category_maps_both_ring_slots_to_the_shared_ring_pool():
    assert world_map.SLOT_CATEGORY["ring_1"] == "ring"
    assert world_map.SLOT_CATEGORY["ring_2"] == "ring"
    assert world_map.SLOT_CATEGORY["helmet"] == "helmet"


# --- The grid map (Super Mario Bros. 3 style) and its rooms ---

def test_every_node_sits_on_its_own_grid_square_and_roads_run_straight():
    from scripts.data_editor import load_world_map_nodes
    nodes, start = load_world_map_nodes()
    squares = [node["grid"] for node in nodes.values()]
    assert len(squares) == len(set(squares)), "two nodes share a square"
    for node_id, node in nodes.items():
        for other in node["connections"]:
            (c1, r1), (c2, r2) = node["grid"], nodes[other]["grid"]
            assert c1 == c2 or r1 == r2, f"road {node_id}-{other} isn't straight"


def test_every_library_and_party_room_has_a_reward():
    from scripts.data_editor import load_world_map_nodes, load_world_map_rooms
    nodes, _ = load_world_map_nodes()
    rooms = load_world_map_rooms()
    room_nodes = [n for n, node in nodes.items() if node["type"] in world_map.ROOM_TYPES]
    assert any(nodes[n]["type"] == "library" for n in room_nodes)
    assert any(nodes[n]["type"] == "party" for n in room_nodes)
    for node_id in room_nodes:
        room = rooms[node_id]
        if nodes[node_id]["type"] == "library":
            assert room["book_turns"] > 0, node_id
        else:
            assert room["exp"] > 0 and room["items"], node_id

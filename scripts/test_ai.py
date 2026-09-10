import random

from scripts import game_logic
from scripts.data_editor import load_dialogues_from_csv


def make_unit(name, team, x, y, faith, mp, skills):
    return game_logic.Unit({
        "name": name,
        "team": team,
        "class": "Knight",
        "x": x,
        "y": y,
        "speed": 10,
        "mv": 3,
        "jump": 1,
        "faith": faith,
        "mp": mp,
        "skills": skills,
        "color": (255, 255, 255),
        "portrait_path": "",
    })


def test_blue_ai_targets_highest_faith_enemy_first():
    game_logic.MAP_DATA = [[0 for _ in range(6)] for _ in range(6)]
    game_logic.MAP_ROWS = 6
    game_logic.MAP_COLS = 6
    game_logic.SKILL_REGISTRY = {
        "Slash": {"mp_cost": 0, "range": 1, "damage": 30, "type": "Physical"},
        "Preach": {"mp_cost": 5, "range": 3, "damage": 50, "type": "Faith"},
    }

    blue = make_unit("Blue Knight", "Blue", 1, 1, 0, 20, ["Slash", "Preach"])
    almost_converted = make_unit("Almost Converted", "Enemy", 2, 1, 90, 0, ["Slash"])
    resistant = make_unit("Resistant", "Enemy", 1, 3, 20, 0, ["Slash"])

    result = game_logic.choose_ai_action(blue, [blue, almost_converted, resistant])
    assert result is not None
    assert result["target"].name == "Almost Converted"


def test_blue_ai_waits_when_no_valid_actions_exist():
    game_logic.MAP_DATA = [[0 for _ in range(6)] for _ in range(6)]
    game_logic.MAP_ROWS = 6
    game_logic.MAP_COLS = 6
    game_logic.SKILL_REGISTRY = {
        "Slash": {"mp_cost": 0, "range": 1, "damage": 30, "type": "Physical"},
    }

    blue = make_unit("Blue Knight", "Blue", 0, 0, 0, 0, ["Slash"])
    enemy = make_unit("Enemy", "Enemy", 5, 5, 0, 0, ["Slash"])

    result = game_logic.choose_ai_action(blue, [blue, enemy])
    assert result is not None
    assert result["action"] == "skip"


def test_healer_ai_heals_lowest_faith_ally_first():
    game_logic.MAP_DATA = [[0 for _ in range(6)] for _ in range(6)]
    game_logic.MAP_ROWS = 6
    game_logic.MAP_COLS = 6
    game_logic.SKILL_REGISTRY = {
        "Chakra": {"mp_cost": 0, "range": 2, "damage": -40, "type": "Heal"},
    }

    healer = make_unit("White Mage", "Blue", 0, 0, 100, 20, ["Chakra"])
    ally1 = make_unit("Frontliner", "Blue", 1, 0, 25, 0, ["Slash"])
    ally2 = make_unit("Support", "Blue", 0, 1, 40, 0, ["Slash"])

    result = game_logic.choose_ai_action(healer, [healer, ally1, ally2])
    assert result["action"] == "skill"
    assert result["target"].name == "Frontliner"


def test_blue_ai_moves_toward_enemy_when_no_valid_attack_exists():
    game_logic.MAP_DATA = [[0 for _ in range(6)] for _ in range(6)]
    game_logic.MAP_ROWS = 6
    game_logic.MAP_COLS = 6
    game_logic.SKILL_REGISTRY = {
        "Slash": {"mp_cost": 0, "range": 1, "damage": 30, "type": "Physical"},
    }

    blue = make_unit("Blue Knight", "Blue", 0, 0, 0, 0, ["Slash"])
    enemy = make_unit("Enemy", "Enemy", 3, 0, 0, 0, ["Slash"])

    move = game_logic.get_ai_move_destination(blue, [blue, enemy])
    assert move == (1, 0) or move == (2, 0)


def test_move_action_is_hidden_when_unit_has_no_reachable_destination():
    game_logic.MAP_DATA = [[0 for _ in range(3)] for _ in range(3)]
    game_logic.MAP_ROWS = 3
    game_logic.MAP_COLS = 3

    unit = make_unit("Trapped Knight", "Blue", 1, 1, 0, 0, [])
    blockers = [
        make_unit("North", "Blue", 1, 0, 0, 0, []),
        make_unit("South", "Blue", 1, 2, 0, 0, []),
        make_unit("West", "Blue", 0, 1, 0, 0, []),
        make_unit("East", "Blue", 2, 1, 0, 0, []),
    ]

    assert game_logic.get_action_menu(unit, [unit, *blockers]) == ["Move", "Act", "Wait"]
    assert not game_logic.can_unit_move(unit, [unit, *blockers])


def test_dialogues_are_loaded_by_character_and_turn():
    dialogues = load_dialogues_from_csv()

    assert dialogues[1][0] == (
        "Judas",
        "(Approaches Jesus with a kiss) Here's the man you want, Romans.",
    )
    assert dialogues[1][-1] == ("James", "Lord, should we strike with our swords?")


def test_fish_net_targets_enemies_and_prevents_movement():
    game_logic.MAP_DATA = [[0 for _ in range(5)] for _ in range(5)]
    game_logic.MAP_ROWS = 5
    game_logic.MAP_COLS = 5
    game_logic.SKILL_REGISTRY = {
        "Fish net": {"mp_cost": 0, "range": 3, "damage": 0, "type": "Status"},
    }

    peter = make_unit("Peter", "Player", 1, 1, 0, 0, ["Fish net"])
    ally = make_unit("Andrew", "Player", 1, 2, 0, 0, [])
    enemy = make_unit("Judas", "Enemy", 2, 1, 0, 0, [])

    targets = game_logic.get_skill_targets(peter, "Fish net", [peter, ally, enemy])
    assert (2, 1) in targets
    assert (1, 2) not in targets

    game_logic.apply_skill_status("Fish net", peter, enemy, [peter, ally, enemy])
    assert enemy.snared_turns == 2
    assert not game_logic.can_unit_move(enemy, [peter, ally, enemy])


def test_shove_on_hit_stuns_and_pushes_target_two_tiles():
    game_logic.MAP_DATA = [[0 for _ in range(6)] for _ in range(6)]
    game_logic.MAP_ROWS = 6
    game_logic.MAP_COLS = 6

    legionnaire = make_unit("Legionnaire", "Enemy", 2, 2, 0, 0, ["Shove"])
    peter = make_unit("Peter", "Player", 3, 2, 0, 0, [])

    random.seed(1)  # first draw is a hit at the current SHOVE_CHANCE
    hit = game_logic.apply_skill_status("Shove", legionnaire, peter, [legionnaire, peter])

    assert hit is True
    assert (peter.x, peter.y) == (5, 2)
    assert peter.stunned_turns == 1


def test_shove_on_miss_leaves_target_unaffected():
    game_logic.MAP_DATA = [[0 for _ in range(6)] for _ in range(6)]
    game_logic.MAP_ROWS = 6
    game_logic.MAP_COLS = 6

    legionnaire = make_unit("Legionnaire", "Enemy", 2, 2, 0, 0, ["Shove"])
    peter = make_unit("Peter", "Player", 3, 2, 0, 0, [])

    random.seed(0)  # first draw is a miss at the current SHOVE_CHANCE
    hit = game_logic.apply_skill_status("Shove", legionnaire, peter, [legionnaire, peter])

    assert hit is False
    assert (peter.x, peter.y) == (3, 2)
    assert peter.stunned_turns == 0

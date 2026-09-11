import glob
import os
import random

import pytest

from scripts import game_logic
from scripts.data_editor import load_dialogues_from_csv, load_skills_from_csv, load_characters_from_csv


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
    dialogues = load_dialogues_from_csv(map_id="jerusalem")

    assert dialogues[1][0] == (
        "Judas",
        "(Approaches Jesus with a kiss) Here's the man you want, Romans.",
    )
    assert dialogues[1][-1] == ("James", "Lord, should we strike with our swords?")


def test_dialogues_are_scoped_per_stage():
    galilee = load_dialogues_from_csv(map_id="galilee")
    jerusalem = load_dialogues_from_csv(map_id="jerusalem")

    assert galilee[1] == [
        ("Jesus", "Come, follow me, and I will send you out to fish for people."),
        ("Peter", "Lord, we have left everything to follow you. A patrol blocks the shore ahead!"),
    ]
    assert all(speaker != "Jesus" or "fish for people" not in text for speaker, text in jerusalem[1])


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


# --- Command / Defend ---

def test_command_boosts_target_ct_capped_at_100():
    officer = make_unit("Centurion", "Enemy", 0, 0, 0, 0, ["Command"])
    soldier = make_unit("Legionnaire", "Enemy", 0, 1, 0, 0, [])
    soldier.ct = 20

    hit = game_logic.apply_skill_status("Command", officer, soldier, [officer, soldier])

    assert hit is True
    assert soldier.ct == 20 + game_logic.COMMAND_CT_BOOST

    soldier.ct = 90
    game_logic.apply_skill_status("Command", officer, soldier, [officer, soldier])
    assert soldier.ct == 100  # clamped, doesn't overshoot


def test_defend_sets_guarded_flag_on_target():
    andrew = make_unit("Andrew", "Player", 0, 0, 0, 0, ["Defend"])
    james = make_unit("James", "Player", 0, 1, 0, 0, [])
    assert james.guarded is False

    hit = game_logic.apply_skill_status("Defend", andrew, james, [andrew, james])

    assert hit is True
    assert james.guarded is True


def test_resolve_physical_hit_kills_unguarded_target():
    attacker = make_unit("Legionnaire", "Enemy", 0, 0, 0, 0, [])
    target = make_unit("Peter", "Player", 0, 1, 0, 0, [])

    killed, message = game_logic.resolve_physical_hit(attacker, target, "Slash")

    assert killed is True
    assert not target.is_alive()
    assert target.removed_at is not None
    assert "strikes down" in message


def test_resolve_physical_hit_blocked_by_guard_and_consumes_it():
    attacker = make_unit("Legionnaire", "Enemy", 0, 0, 0, 0, [])
    target = make_unit("Andrew", "Player", 0, 1, 0, 0, [])
    target.guarded = True

    killed, message = game_logic.resolve_physical_hit(attacker, target, "Slash")

    assert killed is False
    assert target.is_alive()
    assert target.guarded is False  # guard is a one-time block, consumed either way
    assert "guards against" in message


def test_choose_ai_action_targets_ally_with_support_skill():
    game_logic.SKILL_REGISTRY = {
        "Command": {"mp_cost": 0, "range": 4, "damage": 0, "type": "Support"},
    }
    officer = make_unit("Centurion", "Enemy", 0, 0, 0, 0, ["Command"])
    soldier = make_unit("Legionnaire", "Enemy", 0, 1, 0, 0, [])
    enemy_of_officer = make_unit("Peter", "Player", 0, 1, 0, 0, [])

    result = game_logic.choose_ai_action(officer, [officer, soldier, enemy_of_officer])

    assert result["action"] == "skill"
    assert result["target"].name == "Legionnaire"  # never the opposing-team unit


def test_choose_ai_action_command_never_targets_self():
    game_logic.SKILL_REGISTRY = {
        "Command": {"mp_cost": 0, "range": 4, "damage": 0, "type": "Support"},
    }
    officer = make_unit("Centurion", "Enemy", 0, 0, 0, 0, ["Command"])

    result = game_logic.choose_ai_action(officer, [officer])

    assert result["action"] == "skip"


def test_choose_ai_action_defend_skips_already_guarded_allies():
    game_logic.SKILL_REGISTRY = {
        "Defend": {"mp_cost": 0, "range": 4, "damage": 0, "type": "Support"},
    }
    # Andrew is already guarded too, so he isn't the (closer) self-target
    # candidate - this isolates the guarded_ally-vs-unguarded_ally choice.
    andrew = make_unit("Andrew", "Player", 0, 0, 0, 0, ["Defend"])
    andrew.guarded = True
    guarded_ally = make_unit("James", "Player", 0, 1, 0, 0, [])
    guarded_ally.guarded = True
    unguarded_ally = make_unit("John", "Player", 0, 2, 0, 0, [])

    result = game_logic.choose_ai_action(andrew, [andrew, guarded_ally, unguarded_ally])

    assert result["action"] == "skill"
    assert result["target"].name == "John"


def test_choose_ai_action_defend_prefers_self_when_available():
    game_logic.SKILL_REGISTRY = {
        "Defend": {"mp_cost": 0, "range": 4, "damage": 0, "type": "Support"},
    }
    andrew = make_unit("Andrew", "Player", 0, 0, 0, 0, ["Defend"])
    ally = make_unit("James", "Player", 0, 2, 0, 0, [])

    result = game_logic.choose_ai_action(andrew, [andrew, ally])

    assert result["action"] == "skill"
    assert result["target"].name == "Andrew"  # closer (distance 0) than James


def test_get_skill_targets_support_skill_restricted_to_allies():
    game_logic.MAP_DATA = [[0 for _ in range(5)] for _ in range(5)]
    game_logic.MAP_ROWS = 5
    game_logic.MAP_COLS = 5
    game_logic.SKILL_REGISTRY = {
        "Command": {"mp_cost": 0, "range": 4, "damage": 0, "type": "Support"},
    }
    officer = make_unit("Centurion", "Enemy", 2, 2, 0, 0, ["Command"])
    ally = make_unit("Legionnaire", "Enemy", 2, 3, 0, 0, [])
    foe = make_unit("Peter", "Player", 2, 1, 0, 0, [])

    targets = game_logic.get_skill_targets(officer, "Command", [officer, ally, foe])

    assert (2, 3) in targets  # ally tile
    assert (2, 1) not in targets  # enemy tile excluded
    assert (2, 2) not in targets  # Command can't self-target


def test_get_skill_targets_defend_allows_self_target():
    game_logic.MAP_DATA = [[0 for _ in range(5)] for _ in range(5)]
    game_logic.MAP_ROWS = 5
    game_logic.MAP_COLS = 5
    game_logic.SKILL_REGISTRY = {
        "Defend": {"mp_cost": 0, "range": 1, "damage": 0, "type": "Support"},
    }
    andrew = make_unit("Andrew", "Player", 2, 2, 0, 0, ["Defend"])

    targets = game_logic.get_skill_targets(andrew, "Defend", [andrew])

    assert (2, 2) in targets


# --- Faith conversion mechanic (FAITH_CAP rebalance) ---

def test_apply_preach_does_not_convert_below_faith_cap():
    weak_preacher = make_unit("Thomas", "Player", 0, 0, 10, 0, [])  # small gain (2.0)
    judas = make_unit("Judas", "Enemy", 0, 1, 50, 0, [])  # far below the cap

    game_logic.apply_preach(weak_preacher, judas)

    assert judas.team == "Enemy"
    assert judas.faith < game_logic.FAITH_CAP


def test_apply_preach_converts_and_flashes_at_faith_cap():
    jesus = make_unit("Jesus", "Player", 0, 0, 200, 0, [])
    judas = make_unit("Judas", "Enemy", 0, 1, game_logic.FAITH_CAP - 1, 0, [])

    message = game_logic.apply_preach(jesus, judas)

    assert judas.team == "Player"
    assert judas.faith == game_logic.FAITH_CAP
    assert judas.converted_at is not None
    assert "join the Player team" in message


def test_apply_preach_gain_scales_with_preacher_faith():
    weak_preacher = make_unit("Weak", "Player", 0, 0, 50, 0, [])
    strong_preacher = make_unit("Strong", "Player", 0, 0, 200, 0, [])
    target_a = make_unit("Target A", "Enemy", 0, 1, 0, 0, [])
    target_b = make_unit("Target B", "Enemy", 0, 1, 0, 0, [])

    game_logic.apply_preach(weak_preacher, target_a)
    game_logic.apply_preach(strong_preacher, target_b)

    assert target_b.faith > target_a.faith
    assert target_a.faith == pytest.approx(weak_preacher.faith * game_logic.FAITH_TRANSFER_RATE)
    assert target_b.faith == pytest.approx(strong_preacher.faith * game_logic.FAITH_TRANSFER_RATE)


# --- Data integrity: every character skill must exist in skills.csv ---
# (regression test for the "Chakra" skill that was referenced by three
# apostles but never migrated into skills.csv - selecting it would have
# crashed the game with a KeyError)

def test_every_character_skill_is_registered_in_skills_csv():
    registered = set(load_skills_from_csv().keys())

    files = [os.path.join("data", "characters.csv")] + glob.glob(os.path.join("data", "stages", "*", "characters.csv"))
    for path in files:
        for char in load_characters_from_csv(path):
            unknown = set(char["skills"]) - registered
            assert not unknown, f"{char['name']} in {path} uses unregistered skill(s): {unknown}"


# --- predict_turn_order (the turn-order queue UI's underlying simulation) ---

def test_predict_turn_order_favors_higher_speed_proportionally():
    # Speed 20 vs 10 is a 2:1 ratio, so within any settled window the faster
    # unit should act roughly twice as often as the slower one.
    fast = make_unit("Fast", "Player", 0, 0, 0, 0, [])
    fast.speed = 20
    slow = make_unit("Slow", "Enemy", 0, 1, 0, 0, [])
    slow.speed = 10

    order = game_logic.predict_turn_order([fast, slow], count=9)

    assert [u.name for u in order] == ["Fast", "Fast", "Slow"] * 3


def test_predict_turn_order_ready_now_goes_first():
    ready_now = make_unit("ReadyNow", "Player", 0, 0, 0, 0, [])
    ready_now.speed = 10
    ready_now.ct = 100
    not_ready = make_unit("NotReady", "Enemy", 0, 1, 0, 0, [])
    not_ready.speed = 10
    not_ready.ct = 50

    order = game_logic.predict_turn_order([ready_now, not_ready], count=1)

    assert order[0].name == "ReadyNow"


def test_predict_turn_order_does_not_mutate_real_unit_state():
    a = make_unit("A", "Player", 0, 0, 0, 0, [])
    a.speed = 15
    b = make_unit("B", "Enemy", 0, 1, 0, 0, [])
    b.speed = 12
    ct_before = (a.ct, b.ct)

    game_logic.predict_turn_order([a, b], count=10)

    assert (a.ct, b.ct) == ct_before


def test_predict_turn_order_skips_dead_and_disabled_units():
    alive = make_unit("Alive", "Player", 0, 0, 0, 0, [])
    alive.speed = 10
    dead = make_unit("Dead", "Enemy", 0, 1, 0, 0, [])
    dead.speed = 10
    dead.removed = True
    disabled = make_unit("Disabled", "Player", 0, 2, 0, 0, [])
    disabled.speed = 10
    disabled.disabled = True

    order = game_logic.predict_turn_order([alive, dead, disabled], count=5)

    assert all(u.name == "Alive" for u in order)


def test_predict_turn_order_empty_when_no_living_units():
    dead = make_unit("Dead", "Player", 0, 0, 0, 0, [])
    dead.removed = True

    assert game_logic.predict_turn_order([dead], count=5) == []

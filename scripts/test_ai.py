import glob
import os
import random

import pytest

from scripts import game_logic
from scripts.data_editor import load_dialogues_from_csv, load_skills_from_csv, load_characters_from_csv


def make_unit(name, team, x, y, faith, mp, skills, char_class="Knight"):
    return game_logic.Unit({
        "name": name,
        "team": team,
        "class": char_class,
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
    enemy.patience = 0  # isolate this test from Patience's status-resist chance

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
    game_logic.MAP_DATA = [[0 for _ in range(4)] for _ in range(4)]
    attacker = make_unit("Legionnaire", "Enemy", 0, 0, 0, 0, [])
    target = make_unit("Peter", "Player", 0, 1, 0, 0, [])

    random.seed(1)  # a hit at the flat-ground (base) hit chance
    killed, message = game_logic.resolve_physical_hit(attacker, target, "Slash")

    assert killed is True
    assert not target.is_alive()
    assert target.removed_at is not None
    assert "strikes down" in message


def test_resolve_physical_hit_blocked_by_guard_and_consumes_it():
    game_logic.MAP_DATA = [[0 for _ in range(4)] for _ in range(4)]
    attacker = make_unit("Legionnaire", "Enemy", 0, 0, 0, 0, [])
    target = make_unit("Andrew", "Player", 0, 1, 0, 0, [])
    target.guarded = True

    random.seed(1)  # must land the hit first for a guard to have something to block
    killed, message = game_logic.resolve_physical_hit(attacker, target, "Slash")

    assert killed is False
    assert target.is_alive()
    assert target.guarded is False  # guard is a one-time block, consumed either way
    assert "guards against" in message


def test_resolve_physical_hit_can_miss_outright():
    game_logic.MAP_DATA = [[0 for _ in range(4)] for _ in range(4)]
    attacker = make_unit("Legionnaire", "Enemy", 0, 0, 0, 0, [])
    target = make_unit("Peter", "Player", 0, 1, 0, 0, [])

    random.seed(2)  # a miss at the flat-ground (base) hit chance
    killed, message = game_logic.resolve_physical_hit(attacker, target, "Slash")

    assert killed is False
    assert target.is_alive()
    assert "misses" in message


# --- physical_hit_chance (elevation affecting Physical accuracy) ---

def test_physical_hit_chance_is_base_rate_on_flat_ground():
    game_logic.MAP_DATA = [[0 for _ in range(4)] for _ in range(4)]
    attacker = make_unit("Legionnaire", "Enemy", 0, 0, 0, 0, [])
    target = make_unit("Peter", "Player", 0, 1, 0, 0, [])
    target.magic_defense = 0  # isolate from Resist's hit-chance reduction

    assert game_logic.physical_hit_chance(attacker, target) == game_logic.PHYSICAL_BASE_HIT_CHANCE


def test_physical_hit_chance_favors_attacking_from_higher_ground():
    game_logic.MAP_DATA = [
        [1, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    high_ground_attacker = make_unit("Archer", "Enemy", 0, 0, 0, 0, [])  # elevation 1
    low_ground_attacker = make_unit("Archer2", "Enemy", 1, 0, 0, 0, [])  # elevation 0
    target = make_unit("Peter", "Player", 2, 0, 0, 0, [])  # elevation 0
    target.magic_defense = 0  # isolate from Resist's hit-chance reduction

    high_chance = game_logic.physical_hit_chance(high_ground_attacker, target)
    low_chance = game_logic.physical_hit_chance(low_ground_attacker, target)

    assert high_chance > low_chance
    assert high_chance == game_logic.PHYSICAL_BASE_HIT_CHANCE + game_logic.ELEVATION_HIT_BONUS_PER_TILE
    assert low_chance == game_logic.PHYSICAL_BASE_HIT_CHANCE


def test_physical_hit_chance_is_clamped_to_sane_bounds():
    game_logic.MAP_DATA = [
        [50, 0],
        [0, 50],
    ]
    attacker_way_above = make_unit("A", "Enemy", 0, 0, 0, 0, [])  # elevation 50
    target_below = make_unit("TargetBelow", "Player", 1, 0, 0, 0, [])  # elevation 0
    attacker_way_below = make_unit("B", "Enemy", 0, 1, 0, 0, [])  # elevation 0
    target_above = make_unit("TargetAbove", "Player", 1, 1, 0, 0, [])  # elevation 50

    assert game_logic.physical_hit_chance(attacker_way_above, target_below) == game_logic.PHYSICAL_MAX_HIT_CHANCE
    assert game_logic.physical_hit_chance(attacker_way_below, target_above) == game_logic.PHYSICAL_MIN_HIT_CHANCE


def test_physical_hit_chance_is_reduced_by_the_targets_magic_defense():
    game_logic.MAP_DATA = [[0 for _ in range(4)] for _ in range(4)]
    attacker = make_unit("Legionnaire", "Enemy", 0, 0, 0, 0, [])
    armored_target = make_unit("Armored", "Player", 1, 0, 0, 0, [])
    bare_target = make_unit("Bare", "Player", 2, 0, 0, 0, [])
    armored_target.magic_defense = 80
    bare_target.magic_defense = 5

    assert game_logic.physical_hit_chance(attacker, armored_target) < game_logic.physical_hit_chance(attacker, bare_target)


# --- morale_buff_chance / apply_morale_buff (Bravery's morale-buff proc) ---

def test_morale_buff_chance_grows_with_bravery_and_is_capped():
    timid = make_unit("Timid", "Player", 0, 0, 0, 0, [])
    brave = make_unit("Brave", "Player", 0, 0, 0, 0, [])
    timid.bravery = 0
    brave.bravery = 1000  # absurdly high - should still clamp, never guarantee a proc

    assert game_logic.morale_buff_chance(timid) == 0
    assert game_logic.morale_buff_chance(brave) == game_logic.MORALE_CHANCE_CAP


def test_apply_morale_buff_boosts_faith_move_jump_and_speed_on_a_proc(monkeypatch):
    unit = make_unit("Peter", "Player", 0, 0, 100, 0, [])
    unit.bravery = 50
    unit.mv = 3
    unit.jump = 1
    unit.speed = 10
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)  # always procs

    triggered = game_logic.apply_morale_buff(unit)

    assert triggered is True
    assert unit.faith == 100 + game_logic.MORALE_FAITH_BONUS
    assert unit.mv == 3 + game_logic.MORALE_MV_BONUS
    assert unit.jump == 1 + game_logic.MORALE_JUMP_BONUS
    assert unit.speed == 10 + game_logic.MORALE_SPEED_BONUS


def test_apply_morale_buff_does_nothing_when_the_roll_fails(monkeypatch):
    unit = make_unit("Peter", "Player", 0, 0, 100, 0, [])
    unit.bravery = 50
    unit.mv = 3
    unit.jump = 1
    unit.speed = 10
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.99)  # never procs

    triggered = game_logic.apply_morale_buff(unit)

    assert triggered is False
    assert unit.faith == 100
    assert unit.mv == 3
    assert unit.jump == 1
    assert unit.speed == 10


def test_apply_morale_buff_faith_gain_is_capped_at_faith_cap(monkeypatch):
    unit = make_unit("Peter", "Player", 0, 0, game_logic.FAITH_CAP - 2, 0, [])
    unit.bravery = 50
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)  # always procs

    game_logic.apply_morale_buff(unit)

    assert unit.faith == game_logic.FAITH_CAP


# --- status_resist_chance / apply_skill_status (Patience resisting Snare/Stun) ---

def test_status_resist_chance_grows_with_patience_and_is_capped():
    low = make_unit("Low", "Player", 0, 0, 0, 0, [])
    high = make_unit("High", "Player", 0, 0, 0, 0, [])
    low.patience = 0
    high.patience = 1000  # absurdly high - should still clamp, never guarantee immunity

    assert game_logic.status_resist_chance(low) == 0
    assert game_logic.status_resist_chance(high) == game_logic.PATIENCE_RESIST_CAP


def test_apply_skill_status_fish_net_snares_when_patience_roll_fails(monkeypatch):
    caster = make_unit("Peter", "Player", 0, 0, 0, 0, [])
    target = make_unit("Legionnaire", "Enemy", 0, 1, 0, 0, [])
    target.patience = 50
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.99)  # never resists

    assert game_logic.apply_skill_status("Fish net", caster, target, []) is True
    assert target.snared_turns == 2


def test_apply_skill_status_fish_net_is_resisted_when_patience_roll_succeeds(monkeypatch):
    caster = make_unit("Peter", "Player", 0, 0, 0, 0, [])
    target = make_unit("Legionnaire", "Enemy", 0, 1, 0, 0, [])
    target.patience = 50
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)  # always resists

    assert game_logic.apply_skill_status("Fish net", caster, target, []) is False
    assert target.snared_turns == 0


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
    # make_unit doesn't set magic_attack, so both preachers carry the Unit
    # default (25) - it adds directly onto faith in the transfer formula.
    assert target_a.faith == pytest.approx((weak_preacher.faith + weak_preacher.magic_attack) * game_logic.FAITH_TRANSFER_RATE)
    assert target_b.faith == pytest.approx((strong_preacher.faith + strong_preacher.magic_attack) * game_logic.FAITH_TRANSFER_RATE)


def test_apply_preach_gain_also_scales_with_preachers_magic_attack():
    preacher = make_unit("Preacher", "Player", 0, 0, 100, 0, [])
    weaker_preacher = make_unit("Weaker", "Player", 0, 0, 100, 0, [])
    preacher.magic_attack = 50
    weaker_preacher.magic_attack = 0
    target = make_unit("Target", "Enemy", 0, 1, 0, 0, [])
    weaker_target = make_unit("Weaker Target", "Enemy", 0, 1, 0, 0, [])

    game_logic.apply_preach(preacher, target)
    game_logic.apply_preach(weaker_preacher, weaker_target)

    assert target.faith > weaker_target.faith


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


# --- job/class passives ---

def test_soldier_and_sergeant_get_flat_hit_bonus():
    game_logic.MAP_DATA = [[0 for _ in range(4)] for _ in range(4)]
    target = make_unit("Peter", "Player", 0, 1, 0, 0, [])
    knight = make_unit("Grunt", "Enemy", 0, 0, 0, 0, [], char_class="Knight")
    soldier = make_unit("Soldier1", "Enemy", 0, 0, 0, 0, [], char_class="Soldier")
    sergeant = make_unit("Sarge", "Enemy", 0, 0, 0, 0, [], char_class="Sergeant")

    baseline = game_logic.physical_hit_chance(knight, target)

    assert game_logic.physical_hit_chance(soldier, target) == baseline + game_logic.CLASS_HIT_BONUS["Soldier"]
    assert game_logic.physical_hit_chance(sergeant, target) == baseline + game_logic.CLASS_HIT_BONUS["Sergeant"]


def test_archer_ignores_uphill_penalty_but_keeps_downhill_bonus():
    game_logic.MAP_DATA = [
        [0, 3],
        [0, 0],
    ]
    archer = make_unit("Bowman", "Enemy", 0, 0, 0, 0, [], char_class="Archer")  # elevation 0
    knight = make_unit("Grunt", "Enemy", 0, 0, 0, 0, [], char_class="Knight")  # elevation 0
    target_above = make_unit("Peter", "Player", 1, 0, 0, 0, [])  # elevation 3, uphill shot
    target_above.magic_defense = 0  # isolate from Resist's hit-chance reduction

    archer_chance = game_logic.physical_hit_chance(archer, target_above)
    knight_chance = game_logic.physical_hit_chance(knight, target_above)

    assert archer_chance == game_logic.PHYSICAL_BASE_HIT_CHANCE  # penalty ignored, floors at base rate
    assert knight_chance < archer_chance  # a non-archer still suffers the uphill penalty

    game_logic.MAP_DATA = [
        [3, 0],
        [0, 0],
    ]
    high_archer = make_unit("Bowman2", "Enemy", 0, 0, 0, 0, [], char_class="Archer")  # elevation 3
    target_below = make_unit("Andrew", "Player", 1, 0, 0, 0, [])  # elevation 0

    assert game_logic.physical_hit_chance(high_archer, target_below) == game_logic.PHYSICAL_MAX_HIT_CHANCE


def test_officer_aura_boosts_nearby_allies_hit_chance_only():
    game_logic.MAP_DATA = [[0 for _ in range(4)] for _ in range(4)]
    target = make_unit("Peter", "Player", 3, 3, 0, 0, [])
    soldier = make_unit("Soldier1", "Enemy", 0, 0, 0, 0, [], char_class="Knight")
    officer_nearby = make_unit("Officer1", "Enemy", 1, 0, 0, 0, [], char_class="Officer")
    officer_far = make_unit("Officer2", "Enemy", 3, 0, 0, 0, [], char_class="Officer")
    enemy_officer_ally_of_target = make_unit("EnemyOfficer", "Player", 0, 1, 0, 0, [], char_class="Officer")

    no_aura = game_logic.physical_hit_chance(soldier, target, units_list=[soldier, target])
    with_nearby_officer = game_logic.physical_hit_chance(soldier, target, units_list=[soldier, officer_nearby, target])
    with_far_officer_only = game_logic.physical_hit_chance(soldier, target, units_list=[soldier, officer_far, target])
    with_enemy_team_officer = game_logic.physical_hit_chance(
        soldier, target, units_list=[soldier, enemy_officer_ally_of_target, target]
    )

    assert with_nearby_officer == no_aura + game_logic.OFFICER_AURA_HIT_BONUS
    assert with_far_officer_only == no_aura  # out of command range, no bonus
    assert with_enemy_team_officer == no_aura  # an Officer on the target's own team doesn't buff the attacker


def test_prophet_preaches_with_a_faith_multiplier():
    prophet = make_unit("Jesus", "Player", 0, 0, 40, 0, [], char_class="Prophet")
    apostle = make_unit("Peter", "Player", 0, 1, 40, 0, [], char_class="Apostle")
    target_a = make_unit("Enemy1", "Enemy", 0, 2, 50, 0, [])
    target_b = make_unit("Enemy2", "Enemy", 0, 3, 50, 0, [])

    game_logic.apply_preach(prophet, target_a)
    game_logic.apply_preach(apostle, target_b)

    prophet_gain = target_a.faith - 50
    apostle_gain = target_b.faith - 50
    assert prophet_gain == pytest.approx(apostle_gain * game_logic.CLASS_PREACH_MULTIPLIER["Prophet"])


def test_sergeant_shove_pushes_farther_than_default():
    game_logic.MAP_ROWS = 12
    game_logic.MAP_COLS = 12
    units_list = []
    sergeant = make_unit("Sarge", "Enemy", 5, 5, 0, 0, ["Shove"], char_class="Sergeant")
    knight = make_unit("Grunt", "Enemy", 5, 5, 0, 0, ["Shove"], char_class="Knight")
    target_for_sergeant = make_unit("Peter", "Player", 6, 5, 0, 0, [])
    target_for_knight = make_unit("Andrew", "Player", 6, 5, 0, 0, [])
    units_list = [sergeant, target_for_sergeant]

    random.seed(1)  # must succeed the 50% Shove chance roll
    game_logic.apply_skill_status("Shove", sergeant, target_for_sergeant, units_list)
    sergeant_push_distance = target_for_sergeant.x - 6

    units_list2 = [knight, target_for_knight]
    random.seed(1)
    game_logic.apply_skill_status("Shove", knight, target_for_knight, units_list2)
    knight_push_distance = target_for_knight.x - 6

    assert sergeant_push_distance == game_logic.CLASS_SHOVE_DISTANCE["Sergeant"]
    assert knight_push_distance == game_logic.SHOVE_DISTANCE
    assert sergeant_push_distance > knight_push_distance


# --- consumable items (Healing Salve, Ankh, Myrrh, Frankincense, Mustard Seed) ---

def set_item_registry():
    game_logic.ITEM_REGISTRY = {
        "Healing Salve": {"effect": "cure_status", "amount": 0, "target_scope": "ally", "range": 1, "uses": 3, "color": (120, 200, 120)},
        "Ankh": {"effect": "revive", "amount": 0.5, "target_scope": "dead_ally", "range": 2, "uses": 2, "color": (220, 200, 120)},
        "Myrrh": {"effect": "restore_mp", "amount": 0, "target_scope": "ally", "range": 1, "uses": 2, "color": (170, 110, 210)},
        "Frankincense": {"effect": "buff_magic_attack", "amount": 0.3, "target_scope": "ally", "range": 1, "uses": 2, "color": (200, 150, 70)},
        "Mustard Seed": {"effect": "faith_boost", "amount": 20, "target_scope": "ally", "range": 2, "uses": 3, "color": (140, 220, 120)},
    }


def test_get_action_menu_shows_item_only_for_player_team():
    player_unit = make_unit("Peter", "Player", 0, 0, 0, 0, [])
    enemy_unit = make_unit("Legionnaire", "Enemy", 0, 0, 0, 0, [])

    assert game_logic.get_action_menu(player_unit, [player_unit]) == ["Move", "Act", "Item", "Wait"]
    assert game_logic.get_action_menu(enemy_unit, [enemy_unit]) == ["Move", "Act", "Wait"]


def test_get_item_targets_finds_living_ally_including_self_within_range():
    set_item_registry()
    game_logic.MAP_ROWS = 5
    game_logic.MAP_COLS = 5
    user = make_unit("Peter", "Player", 2, 2, 0, 0, [])
    nearby_ally = make_unit("Andrew", "Player", 2, 3, 0, 0, [])
    far_ally = make_unit("John", "Player", 4, 4, 0, 0, [])
    enemy = make_unit("Legionnaire", "Enemy", 2, 1, 0, 0, [])
    units_list = [user, nearby_ally, far_ally, enemy]

    targets = game_logic.get_item_targets(user, "Healing Salve", units_list)  # range 1

    assert (2, 2) in targets  # self
    assert (2, 3) in targets  # adjacent ally
    assert (4, 4) not in targets  # out of range
    assert (2, 1) not in targets  # enemy tile excluded


def test_get_item_targets_dead_ally_only_finds_removed_teammates():
    set_item_registry()
    game_logic.MAP_ROWS = 5
    game_logic.MAP_COLS = 5
    user = make_unit("Peter", "Player", 2, 2, 0, 0, [])
    fallen_ally = make_unit("Andrew", "Player", 2, 3, 0, 0, [])
    fallen_ally.removed = True
    living_ally = make_unit("John", "Player", 2, 1, 0, 0, [])
    fallen_enemy = make_unit("Legionnaire", "Enemy", 1, 2, 0, 0, [])
    fallen_enemy.removed = True
    units_list = [user, fallen_ally, living_ally, fallen_enemy]

    targets = game_logic.get_item_targets(user, "Ankh", units_list)  # range 2, dead_ally

    assert (2, 3) in targets  # fallen ally
    assert (2, 1) not in targets  # living ally isn't a valid Ankh target
    assert (1, 2) not in targets  # a fallen ENEMY isn't a valid Ankh target either


def test_apply_item_effect_healing_salve_cures_status_ailments():
    set_item_registry()
    user = make_unit("Peter", "Player", 0, 0, 0, 0, [])
    target = make_unit("Andrew", "Player", 0, 1, 0, 0, [])
    target.stunned_turns = 1
    target.snared_turns = 2

    message = game_logic.apply_item_effect("Healing Salve", user, target)

    assert target.stunned_turns == 0
    assert target.snared_turns == 0
    assert "Healing Salve" in message


def test_apply_item_effect_ankh_revives_scaled_by_users_faith():
    set_item_registry()
    user = make_unit("Peter", "Player", 0, 0, 60, 0, [])
    fallen_ally = make_unit("Andrew", "Player", 0, 1, 0, 0, [])
    fallen_ally.removed = True
    fallen_ally.removed_at = 1234

    message = game_logic.apply_item_effect("Ankh", user, fallen_ally)

    assert fallen_ally.is_alive()
    assert fallen_ally.removed_at is None
    # make_unit doesn't set love, so it carries the Unit default (25) - Love
    # adds straight onto the revived Faith, on top of the Faith fraction.
    assert fallen_ally.faith == round(60 * 0.5) + user.love
    assert "Ankh" in message


def test_apply_item_effect_ankh_revive_floors_at_minimum_faith():
    set_item_registry()
    weak_user = make_unit("Peter", "Player", 0, 0, 5, 0, [])  # 5 * 0.5 = 2.5, below the floor
    weak_user.love = 0  # isolate the floor behavior from Love's bonus
    fallen_ally = make_unit("Andrew", "Player", 0, 1, 0, 0, [])
    fallen_ally.removed = True

    game_logic.apply_item_effect("Ankh", weak_user, fallen_ally)

    assert fallen_ally.faith == game_logic.ANKH_MIN_REVIVE_FAITH


def test_apply_item_effect_ankh_revive_boosted_by_users_love():
    set_item_registry()
    user = make_unit("Peter", "Player", 0, 0, 60, 0, [])
    user.love = 40
    fallen_ally = make_unit("Andrew", "Player", 0, 1, 0, 0, [])
    fallen_ally.removed = True

    game_logic.apply_item_effect("Ankh", user, fallen_ally)

    assert fallen_ally.faith == round(60 * 0.5) + 40


def test_apply_item_effect_myrrh_fully_restores_mp():
    set_item_registry()
    user = make_unit("Peter", "Player", 0, 0, 0, 0, [])
    target = make_unit("Andrew", "Player", 0, 1, 0, 30, [])
    target.mp = 5

    game_logic.apply_item_effect("Myrrh", user, target)

    assert target.mp == target.max_mp == 30


def test_apply_item_effect_frankincense_buffs_magic_attack_from_users_stat():
    set_item_registry()
    user = make_unit("Peter", "Player", 0, 0, 0, 0, [])
    user.magic_attack = 40
    target = make_unit("Andrew", "Player", 0, 1, 0, 0, [])
    target.magic_attack = 10

    game_logic.apply_item_effect("Frankincense", user, target)

    assert target.magic_attack == 10 + round(40 * 0.3)


def test_apply_item_effect_mustard_seed_grants_flat_faith_clamped_to_cap():
    set_item_registry()
    user = make_unit("Peter", "Player", 0, 0, 0, 0, [])
    target = make_unit("Andrew", "Player", 0, 1, 190, 0, [])

    game_logic.apply_item_effect("Mustard Seed", user, target)

    assert target.faith == game_logic.FAITH_CAP  # 190 + 20 clamps at the cap


def test_find_item_target_matches_get_item_targets_for_dead_ally_scope():
    set_item_registry()
    user = make_unit("Peter", "Player", 0, 0, 0, 0, [])
    fallen_ally = make_unit("Andrew", "Player", 0, 1, 0, 0, [])
    fallen_ally.removed = True
    units_list = [user, fallen_ally]

    found = game_logic.find_item_target(units_list, 0, 1, "Ankh", "Player")

    assert found is fallen_ally


# --- equipment (world map gear that carries a flat stat bonus into battle) ---

def set_equipment_registry():
    game_logic.EQUIPMENT_REGISTRY = {
        "Bronze Helm": {"slot": "helmet", "stats": {"magic_defense": 8}, "description": ""},
        "Helmet of Salvation": {"slot": "helmet", "stats": {"faith": 15, "magic_defense": 5}, "description": ""},
        "Sword of the Spirit": {"slot": "right_hand", "stats": {"magic_attack": 15, "bravery": 10}, "description": ""},
    }


def test_apply_equipment_bonuses_adds_every_equipped_items_stats():
    set_equipment_registry()
    unit = make_unit("Peter", "Player", 0, 0, 0, 0, [])
    unit.magic_defense = 10
    unit.magic_attack = 5
    unit.faith = 20
    unit.bravery = 10
    unit.equipment = {"helmet": "Helmet of Salvation", "right_hand": "Sword of the Spirit"}

    game_logic.apply_equipment_bonuses(unit)

    assert unit.faith == 20 + 15
    assert unit.magic_defense == 10 + 5
    assert unit.magic_attack == 5 + 15
    assert unit.bravery == 10 + 10


def test_apply_equipment_bonuses_ignores_empty_slots_and_unknown_items():
    set_equipment_registry()
    unit = make_unit("Peter", "Player", 0, 0, 0, 0, [])
    unit.magic_defense = 10
    unit.equipment = {"helmet": None, "armor": "Something Not In The Catalog", "right_hand": None}

    game_logic.apply_equipment_bonuses(unit)

    assert unit.magic_defense == 10  # unchanged - nothing valid was equipped


def test_unit_defaults_to_no_equipment():
    unit = make_unit("Peter", "Player", 0, 0, 0, 0, [])
    assert unit.equipment == {}

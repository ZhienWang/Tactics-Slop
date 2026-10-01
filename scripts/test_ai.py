import glob
import os
import random

import pytest

from scripts import game_logic
from scripts.data_editor import load_dialogues_from_csv, load_skills_from_csv, load_characters_from_csv, load_stage_manifest, load_escape_tiles_from_csv


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
    dialogues = load_dialogues_from_csv(map_id="rome")

    assert dialogues[1][0] == (
        "Demas",
        "(Slips toward the Forum) I have loved this present world too much, Paul. Rome's favor is worth more to me than your chains.",
    )
    assert dialogues[1][-1] == ("Silas", "Paul, should we resist when the guard comes for us?")


def test_dialogues_are_scoped_per_stage():
    jerusalem = load_dialogues_from_csv(map_id="jerusalem")
    rome = load_dialogues_from_csv(map_id="rome")

    assert jerusalem[1] == [
        ("Paul", "I persecuted the church of God and tried to destroy it, but God, who set me apart before I was born, was pleased to reveal his Son to me."),
        ("Barnabas", "The believers still fear you, Paul, and the temple guard has marked this house. Stand ready, all of you."),
    ]
    assert all(speaker != "Demas" for speaker, text in jerusalem[1])
    assert any(speaker == "Demas" for speaker, text in rome[1])


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
    """Shoot still strikes down; Slash only disarms (see below)."""
    game_logic.MAP_DATA = [[0 for _ in range(4)] for _ in range(4)]
    attacker = make_unit("Legionnaire", "Enemy", 0, 0, 0, 0, [])
    target = make_unit("Peter", "Player", 0, 1, 0, 0, [])

    random.seed(1)  # a hit at the flat-ground (base) hit chance
    killed, message = game_logic.resolve_physical_hit(attacker, target, "Shoot")

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

    assert game_logic.morale_buff_chance(timid) == game_logic.MORALE_BASE_CHANCE  # the dice baseline
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
    paul = make_unit("Paul", "Player", 0, 0, 200, 0, [])
    judas = make_unit("Judas", "Enemy", 0, 1, game_logic.FAITH_CAP - 1, 0, [])

    message = game_logic.apply_preach(paul, judas)

    assert judas.team == "Player"
    assert judas.faith == game_logic.SIDE_SWITCH_FAITH  # a young faith on the new side
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


def test_enemy_preach_lowers_player_faith():
    legionnaire = make_unit("Legionnaire", "Enemy", 0, 0, 100, 0, [])
    peter = make_unit("Peter", "Player", 0, 1, 120, 0, [])

    message = game_logic.apply_preach(legionnaire, peter)

    expected_loss = (legionnaire.faith + legionnaire.magic_attack) * game_logic.FAITH_TRANSFER_RATE
    assert peter.faith == pytest.approx(120 - expected_loss)
    assert peter.faith_popup["amount"] < 0
    assert "doubt" in message


def test_enemy_preach_cannot_drop_player_faith_below_zero():
    legionnaire = make_unit("Legionnaire", "Enemy", 0, 0, 200, 0, [])
    peter = make_unit("Peter", "Player", 0, 1, 5, 0, [])

    game_logic.apply_preach(legionnaire, peter)

    assert peter.faith == 0


def test_enemy_healing_an_ally_still_raises_faith():
    medic = make_unit("Medic", "Enemy", 0, 0, 100, 0, [])
    legionnaire = make_unit("Legionnaire", "Enemy", 0, 1, 20, 0, [])

    game_logic.apply_preach(medic, legionnaire)

    assert legionnaire.faith > 20


def test_player_falls_into_despair_when_faith_hits_zero():
    legionnaire = make_unit("Legionnaire", "Enemy", 0, 0, 200, 0, [])
    peter = make_unit("Peter", "Player", 0, 1, 5, 0, [])

    message = game_logic.apply_preach(legionnaire, peter)

    assert peter.despair_turns == game_logic.DESPAIR_TURNS
    assert "despair" in message


def test_despair_is_not_reset_by_further_preaching():
    legionnaire = make_unit("Legionnaire", "Enemy", 0, 0, 200, 0, [])
    peter = make_unit("Peter", "Player", 0, 1, 5, 0, [])
    game_logic.apply_preach(legionnaire, peter)
    game_logic.tick_despair(peter)

    game_logic.apply_preach(legionnaire, peter)

    assert peter.despair_turns == game_logic.DESPAIR_TURNS - 1


def test_despair_skips_three_turns_then_recovers():
    peter = make_unit("Peter", "Player", 0, 1, 0, 0, [])
    game_logic.enter_despair_if_faithless(peter)

    logs = [game_logic.tick_despair(peter) for _ in range(game_logic.DESPAIR_TURNS)]

    assert all(logs)  # each of those turns is lost
    assert "rekindled" in logs[-1]
    assert peter.despair_turns == 0
    assert peter.faith == game_logic.DESPAIR_RECOVERY_FAITH
    assert game_logic.tick_despair(peter) is None  # the next turn is a normal one


def test_enemy_units_never_fall_into_despair():
    legionnaire = make_unit("Legionnaire", "Enemy", 0, 0, 0, 0, [])

    assert not game_logic.enter_despair_if_faithless(legionnaire)
    assert legionnaire.despair_turns == 0


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


def test_missionary_preaches_with_a_faith_multiplier():
    missionary = make_unit("Paul", "Player", 0, 0, 40, 0, [], char_class="Missionary")
    apostle = make_unit("Peter", "Player", 0, 1, 40, 0, [], char_class="Apostle")
    target_a = make_unit("Enemy1", "Enemy", 0, 2, 50, 0, [])
    target_b = make_unit("Enemy2", "Enemy", 0, 3, 50, 0, [])

    game_logic.apply_preach(missionary, target_a)
    game_logic.apply_preach(apostle, target_b)

    missionary_gain = target_a.faith - 50
    apostle_gain = target_b.faith - 50
    assert missionary_gain == pytest.approx(apostle_gain * game_logic.CLASS_PREACH_MULTIPLIER["Missionary"])


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


# --- Battle preview (predict_action) ---

PREVIEW_SKILLS = {
    "Preach": {"mp_cost": 0, "range": 1, "damage": 30, "type": "Faith", "color": (255, 215, 0)},
    "Slash": {"mp_cost": 0, "range": 1, "damage": 45, "type": "Physical", "color": (255, 100, 50)},
    "Shove": {"mp_cost": 0, "range": 1, "damage": 0, "type": "Status", "color": (220, 40, 40)},
}


def test_preview_preach_matches_what_preach_actually_does():
    game_logic.SKILL_REGISTRY = PREVIEW_SKILLS
    paul = make_unit("Paul", "Player", 0, 0, 100, 0, [])
    judas = make_unit("Judas", "Enemy", 0, 1, 40, 0, [])

    prediction = game_logic.predict_action(paul, judas, "Preach")
    game_logic.apply_preach(paul, judas)

    assert prediction["chance"] == game_logic.faith_hit_chance(paul)
    assert prediction["faith_before"] == 40
    assert prediction["faith_after"] == pytest.approx(judas.faith)
    assert prediction["outcome"] == "Faith up"


def test_preview_flags_a_conversion():
    game_logic.SKILL_REGISTRY = PREVIEW_SKILLS
    paul = make_unit("Paul", "Player", 0, 0, 200, 0, [])
    judas = make_unit("Judas", "Enemy", 0, 1, game_logic.FAITH_CAP - 1, 0, [])

    assert game_logic.predict_action(paul, judas, "Preach")["outcome"] == "CONVERT!"
    assert judas.team == "Enemy"  # predicting changes nothing


def test_preview_slash_uses_the_physical_hit_chance():
    game_logic.SKILL_REGISTRY = PREVIEW_SKILLS
    game_logic.MAP_DATA = [[0 for _ in range(6)] for _ in range(6)]
    mark = make_unit("Mark", "Player", 0, 0, 100, 0, [])
    soldier = make_unit("Soldier", "Enemy", 0, 1, 100, 0, [])

    prediction = game_logic.predict_action(mark, soldier, "Slash")

    assert prediction["chance"] == game_logic.physical_hit_chance(mark, soldier)
    assert prediction["outcome"] == f"Disarm {game_logic.DISARM_TURNS} turns"


def test_preview_slash_on_a_guarded_target_shows_the_block():
    game_logic.SKILL_REGISTRY = PREVIEW_SKILLS
    game_logic.MAP_DATA = [[0 for _ in range(6)] for _ in range(6)]
    mark = make_unit("Mark", "Player", 0, 0, 100, 0, [])
    soldier = make_unit("Soldier", "Enemy", 0, 1, 100, 0, [])
    soldier.guarded = True

    prediction = game_logic.predict_action(mark, soldier, "Slash")

    assert prediction["chance"] == 0.0
    assert soldier.guarded  # predicting doesn't spend the guard


def test_preview_shove_accounts_for_the_targets_patience():
    game_logic.SKILL_REGISTRY = PREVIEW_SKILLS
    mark = make_unit("Mark", "Player", 0, 0, 100, 0, [])
    soldier = make_unit("Soldier", "Enemy", 0, 1, 100, 0, [])

    prediction = game_logic.predict_action(mark, soldier, "Shove")

    assert prediction["chance"] == pytest.approx(game_logic.SHOVE_CHANCE * (1 - game_logic.status_resist_chance(soldier)))


# --- Faith attack accuracy (Love) ---

def test_faith_hit_chance_grows_with_love():
    cold = make_unit("Cold", "Player", 0, 0, 100, 0, [])
    warm = make_unit("Warm", "Player", 0, 0, 100, 0, [])
    cold.love, warm.love = 5, 40

    assert game_logic.faith_hit_chance(warm) > game_logic.faith_hit_chance(cold)
    assert game_logic.faith_hit_chance(cold) == pytest.approx(game_logic.FAITH_BASE_HIT_CHANCE + 5 * game_logic.FAITH_HIT_PER_LOVE)


def test_faith_hit_chance_is_clamped():
    saint = make_unit("Saint", "Player", 0, 0, 100, 0, [])
    saint.love = 500
    stone = make_unit("Stone", "Player", 0, 0, 100, 0, [])
    stone.love = -100

    assert game_logic.faith_hit_chance(saint) == game_logic.FAITH_MAX_HIT_CHANCE
    assert game_logic.faith_hit_chance(stone) == game_logic.FAITH_MIN_HIT_CHANCE


def test_missed_faith_attack_leaves_target_faith_unchanged(monkeypatch):
    paul = make_unit("Paul", "Player", 0, 0, 100, 0, [])
    judas = make_unit("Judas", "Enemy", 0, 1, 40, 0, [])
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.999)  # above any hit chance

    message = game_logic.resolve_faith_attack(paul, judas)

    assert judas.faith == 40
    assert "Miss" in message


def test_landed_faith_attack_applies_preach(monkeypatch):
    paul = make_unit("Paul", "Player", 0, 0, 100, 0, [])
    judas = make_unit("Judas", "Enemy", 0, 1, 40, 0, [])
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)

    game_logic.resolve_faith_attack(paul, judas)

    assert judas.faith > 40


# --- Lead (Paul's area Love buff) ---

LEAD_SKILLS = {"Lead": {"mp_cost": 50, "range": 0, "damage": 0, "type": "Support", "color": (255, 200, 0)}}


def test_lead_gives_love_to_allies_within_two_tiles_including_the_leader():
    game_logic.SKILL_REGISTRY = LEAD_SKILLS
    paul = make_unit("Paul", "Player", 2, 2, 100, 100, ["Lead"])
    near = make_unit("Near", "Player", 3, 3, 100, 0, [])      # 2 tiles away
    far = make_unit("Far", "Player", 5, 2, 100, 0, [])        # 3 tiles away
    enemy = make_unit("Enemy", "Enemy", 2, 3, 100, 0, [])
    units = [paul, near, far, enemy]
    before = {u.name: u.love for u in units}

    assert game_logic.apply_skill_status("Lead", paul, paul, units)

    assert paul.love == before["Paul"] + game_logic.LEAD_LOVE_BONUS
    assert near.love == before["Near"] + game_logic.LEAD_LOVE_BONUS
    assert far.love == before["Far"]
    assert enemy.love == before["Enemy"]


def test_relead_refreshes_turns_without_stacking_love():
    game_logic.SKILL_REGISTRY = LEAD_SKILLS
    paul = make_unit("Paul", "Player", 2, 2, 100, 100, ["Lead"])
    game_logic.apply_skill_status("Lead", paul, paul, [paul])
    love_once = paul.love
    game_logic.tick_lead(paul)

    assert game_logic.apply_skill_status("Lead", paul, paul, [paul])
    assert paul.love == love_once
    assert paul.lead_turns == game_logic.LEAD_TURNS


def test_lead_lasts_three_turns_then_wears_off():
    paul = make_unit("Paul", "Player", 2, 2, 100, 100, ["Lead"])
    base_love = paul.love
    game_logic.apply_skill_status("Lead", paul, paul, [paul])

    for _ in range(game_logic.LEAD_TURNS):  # each of the next 3 turns is led
        assert not game_logic.tick_lead(paul)
        assert paul.love == base_love + game_logic.LEAD_LOVE_BONUS

    assert game_logic.tick_lead(paul)  # the 4th turn starts without it
    assert paul.love == base_love
    assert not game_logic.tick_lead(paul)
    assert paul.love == base_love


def test_lead_targets_only_the_leaders_own_tile():
    game_logic.MAP_DATA = [[0 for _ in range(5)] for _ in range(5)]
    game_logic.MAP_ROWS = game_logic.MAP_COLS = 5
    game_logic.SKILL_REGISTRY = LEAD_SKILLS
    paul = make_unit("Paul", "Player", 2, 2, 100, 100, ["Lead"])

    assert game_logic.get_skill_targets(paul, "Lead", [paul]) == [(2, 2)]


def test_lead_raises_preach_accuracy():
    paul = make_unit("Paul", "Player", 0, 0, 100, 100, [])
    paul.love = 20
    before = game_logic.faith_hit_chance(paul)
    game_logic.apply_skill_status("Lead", paul, paul, [paul])

    assert game_logic.faith_hit_chance(paul) > before



# --- Slash disarms instead of killing ---

def test_slash_disarms_for_two_turns_instead_of_killing(monkeypatch):
    game_logic.MAP_DATA = [[0 for _ in range(4)] for _ in range(4)]
    mark = make_unit("Mark", "Player", 0, 0, 100, 0, [])
    soldier = make_unit("Soldier", "Enemy", 0, 1, 100, 0, [])
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)

    killed, message = game_logic.resolve_physical_hit(mark, soldier, "Slash")

    assert killed is False and soldier.is_alive()
    assert soldier.disarmed_turns == 2
    assert "disarms" in message


def test_disarmed_unit_cannot_act_for_its_next_two_turns_then_recovers():
    soldier = make_unit("Soldier", "Enemy", 0, 1, 100, 0, [])
    soldier.disarmed_turns = game_logic.DISARM_TURNS
    for _ in range(2):
        assert game_logic.begin_turn(soldier)["disarmed"]
        assert soldier.has_acted  # Act and Item are off the menu
        assert game_logic.choose_ai_action(soldier, [soldier])["action"] == "skip"
    assert not game_logic.begin_turn(soldier)["disarmed"]
    assert not soldier.has_acted


# --- Morale: once per battle, one turn ---

def test_morale_fires_only_once_per_battle(monkeypatch):
    unit = make_unit("Peter", "Player", 0, 0, 100, 0, [])
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)
    assert game_logic.apply_morale_buff(unit)
    game_logic.end_morale_buff(unit)
    assert not game_logic.apply_morale_buff(unit)


def test_morale_lasts_only_one_turn(monkeypatch):
    unit = make_unit("Peter", "Player", 0, 0, 100, 0, [])
    unit.mv, unit.jump, unit.speed = 3, 1, 10
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)
    game_logic.begin_turn(unit)  # morale fires this turn
    assert unit.mv == 4 and unit.speed == 15
    game_logic.begin_turn(unit)  # next turn: taken back, and never again
    assert (unit.mv, unit.jump, unit.speed) == (3, 1, 10)


# --- AI targeting ---

def test_enemy_preach_goes_after_the_lowest_faith_player():
    game_logic.MAP_DATA = [[0 for _ in range(6)] for _ in range(6)]
    game_logic.MAP_ROWS = game_logic.MAP_COLS = 6
    game_logic.SKILL_REGISTRY = {"Preach": {"mp_cost": 0, "range": 3, "damage": 30, "type": "Faith"}}
    legionnaire = make_unit("Legionnaire", "Enemy", 2, 2, 100, 0, ["Preach"])
    strong = make_unit("Paul", "Player", 2, 3, 180, 0, [])
    weak = make_unit("Mark", "Player", 3, 3, 40, 0, [])

    result = game_logic.choose_ai_action(legionnaire, [legionnaire, strong, weak])

    assert result["target"].name == "Mark"


def test_ai_shoves_into_a_cluster_but_not_a_lone_unit():
    game_logic.MAP_DATA = [[0 for _ in range(6)] for _ in range(6)]
    game_logic.MAP_ROWS = game_logic.MAP_COLS = 6
    game_logic.SKILL_REGISTRY = {
        "Preach": {"mp_cost": 0, "range": 1, "damage": 30, "type": "Faith"},
        "Shove": {"mp_cost": 0, "range": 1, "damage": 0, "type": "Status"},
    }
    legionnaire = make_unit("Legionnaire", "Enemy", 2, 2, 100, 0, ["Preach", "Shove"])
    peter = make_unit("Peter", "Player", 2, 3, 100, 0, [])

    alone = game_logic.choose_ai_action(legionnaire, [legionnaire, peter])
    assert alone["skill"] == "Preach"

    john = make_unit("John", "Player", 3, 3, 100, 0, [])  # standing next to Peter
    clustered = game_logic.choose_ai_action(legionnaire, [legionnaire, peter, john])
    assert clustered["skill"] == "Shove"


def test_converted_units_cannot_be_targeted_by_either_side():
    game_logic.MAP_DATA = [[0 for _ in range(6)] for _ in range(6)]
    game_logic.MAP_ROWS = game_logic.MAP_COLS = 6
    game_logic.SKILL_REGISTRY = {
        "Preach": {"mp_cost": 0, "range": 3, "damage": 30, "type": "Faith"},
        "Heal": {"mp_cost": 0, "range": 3, "damage": -40, "type": "Heal"},
    }
    convert = make_unit("Convert", "Player", 2, 3, 150, 0, [])
    convert.disabled = True
    legionnaire = make_unit("Legionnaire", "Enemy", 2, 2, 100, 0, ["Preach"])
    paul = make_unit("Paul", "Player", 4, 4, 100, 0, ["Heal"])
    units = [convert, legionnaire, paul]

    # The convert is the only unit in range - so the Legionnaire has nobody to act on.
    assert game_logic.choose_ai_action(legionnaire, units).get("target") is not convert
    assert (2, 3) not in game_logic.get_skill_targets(paul, "Heal", units)
    assert (2, 3) not in game_logic.get_skill_targets(legionnaire, "Preach", units)


# --- Stage data ---

def test_rome_fields_seven_enemies():
    rome = load_characters_from_csv(os.path.join(game_logic.os.path.dirname(game_logic.os.path.dirname(__file__)), "data", "stages", "rome", "characters.csv"))
    assert sum(1 for c in rome if c["team"] != "Player") == 7


def test_enemy_levels_rise_stage_by_stage():
    root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "stages")
    order = ["jerusalem", "antioch", "philippi", "corinth", "ephesus", "rome"]
    levels = []
    for stage in order:
        enemies = [c for c in load_characters_from_csv(os.path.join(root, stage, "characters.csv")) if c["team"] != "Player"]
        levels.append(min(c["level"] for c in enemies))
    assert levels == sorted(levels) and levels[0] == 1 and levels[-1] > levels[0]


def test_players_still_start_at_level_one_everywhere():
    root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "stages")
    for stage in os.listdir(root):
        path = os.path.join(root, stage, "characters.csv")
        if os.path.exists(path):
            for c in load_characters_from_csv(path):
                if c["team"] == "Player":
                    assert c["level"] == 1, (stage, c["name"])


def test_enemies_have_varied_skill_sets():
    root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "stages")
    for stage in ["jerusalem", "ephesus"]:
        soldiers = [c for c in load_characters_from_csv(os.path.join(root, stage, "characters.csv")) if c["team"] != "Player"]
        assert len({"|".join(c["skills"]) for c in soldiers}) >= 3, stage


# --- Legionnaire subclasses ---

def test_shieldbearers_start_guarded_and_are_harder_to_hit():
    attacker = make_unit("Mark", "Player", 0, 0, 100, 0, ["Slash"])
    shieldbearer = make_unit("Shield", "Enemy", 1, 0, 100, 0, [], char_class="Shieldbearer")
    medic = make_unit("Medic", "Enemy", 1, 0, 100, 0, [], char_class="Medic")
    assert shieldbearer.guarded and not medic.guarded
    shieldbearer.magic_defense = medic.magic_defense = 0
    penalty = game_logic.CLASS_HIT_PENALTY_AGAINST["Shieldbearer"]
    assert game_logic.physical_hit_chance(attacker, shieldbearer) == pytest.approx(game_logic.physical_hit_chance(attacker, medic) - penalty)


def test_rally_pulls_faith_back_toward_baseline_and_clears_statuses():
    medic = make_unit("Medic", "Enemy", 0, 0, 100, 0, ["Rally"], char_class="Medic")
    ally = make_unit("Ally", "Enemy", 1, 0, 180, 0, [])
    ally.stunned_turns, ally.snared_turns, ally.disarmed_turns = 1, 2, 2
    assert game_logic.apply_skill_status("Rally", medic, ally, [medic, ally])
    assert ally.faith == 180 - game_logic.RALLY_FAITH_RESTORE
    assert (ally.stunned_turns, ally.snared_turns, ally.disarmed_turns) == (0, 0, 0)

    nearly_steady = make_unit("Ally2", "Enemy", 1, 0, 110, 0, [])
    game_logic.apply_skill_status("Rally", medic, nearly_steady, [medic, nearly_steady])
    assert nearly_steady.faith == game_logic.RALLY_BASELINE_FAITH  # never below where enemies start

    steady = make_unit("Ally3", "Enemy", 1, 0, 100, 0, [])
    assert not game_logic.apply_skill_status("Rally", medic, steady, [medic, steady])


def test_ai_medic_rallies_the_ally_closest_to_conversion():
    game_logic.SKILL_REGISTRY = {"Rally": {"mp_cost": 0, "range": 2, "damage": 0, "type": "Support", "color": (120, 200, 160)}}
    medic = make_unit("Medic", "Enemy", 0, 0, 100, 0, ["Rally"], char_class="Medic")
    wavering = make_unit("Wavering", "Enemy", 1, 0, 190, 0, [])
    doubting = make_unit("Doubting", "Enemy", 0, 1, 120, 0, [])
    steady = make_unit("Steady", "Enemy", 1, 1, 100, 0, [])
    paul = make_unit("Paul", "Player", 5, 5, 200, 0, [])
    choice = game_logic.choose_ai_action(medic, [medic, wavering, doubting, steady, paul])
    assert choice["skill"] == "Rally" and choice["target"] is wavering

    wavering.faith = doubting.faith = 100
    assert game_logic.choose_ai_action(medic, [medic, wavering, doubting, steady, paul])["action"] == "skip"


# --- Conversion back and forth, fleeing ---

def test_converted_enemies_join_the_player_side_and_take_turns():
    paul = make_unit("Paul", "Player", 0, 0, 200, 0, [])
    legionnaire = make_unit("Legionnaire Medic 1", "Enemy", 0, 1, game_logic.FAITH_CAP - 1, 0, ["Rally"], char_class="Medic")
    legionnaire.portrait_path = legionnaire.original_portrait_path = "assets/legionaire.png"
    legionnaire.stunned_turns = 1
    game_logic.apply_preach(paul, legionnaire)
    assert legionnaire.team == "Player" and legionnaire.converted
    assert not legionnaire.disabled and game_logic.targetable(legionnaire)
    assert legionnaire.stunned_turns == 0
    assert legionnaire.portrait_path == "assets/legionaire_converted.png"
    assert not game_logic.is_ai_team(legionnaire.team)  # the player commands them now
    assert legionnaire in game_logic.predict_turn_order([paul, legionnaire], count=4)


def test_a_convert_shaken_to_zero_turns_back_instead_of_despairing():
    convert = make_unit("Legionnaire Archer 1", "Enemy", 0, 1, 10, 0, [])
    convert.portrait_path = convert.original_portrait_path = "assets/legionaire.png"
    game_logic.convert_unit(convert, "Player", 0)
    convert.faith = 5
    legionnaire = make_unit("Legionnaire 2", "Enemy", 0, 0, 100, 0, [])
    message = game_logic.apply_preach(legionnaire, convert)
    assert convert.team == "Enemy" and not convert.converted
    assert convert.faith == game_logic.SIDE_SWITCH_FAITH and convert.despair_turns == 0
    assert convert.portrait_path == "assets/legionaire.png"
    assert "turn back" in message

    # ...and they can be preached over again.
    convert.faith = game_logic.FAITH_CAP - 1
    game_logic.apply_preach(make_unit("Paul", "Player", 1, 1, 200, 0, []), convert)
    assert convert.team == "Player" and convert.converted


def test_original_party_members_still_fall_into_despair():
    peter = make_unit("Peter", "Player", 0, 1, 5, 0, [])
    game_logic.apply_preach(make_unit("Legionnaire 1", "Enemy", 0, 0, 100, 0, []), peter)
    assert peter.team == "Player" and peter.despair_turns == game_logic.DESPAIR_TURNS


def test_converted_medics_rally_raises_their_new_allies_faith():
    medic = make_unit("Legionnaire Medic 1", "Enemy", 0, 0, 200, 0, ["Rally"], char_class="Medic")
    game_logic.convert_unit(medic, "Player", 0)
    peter = make_unit("Peter", "Player", 0, 1, 50, 0, [])
    game_logic.apply_skill_status("Rally", medic, peter, [medic, peter])
    assert peter.faith == 50 + game_logic.RALLY_FAITH_RESTORE


def test_legionnaires_flee_more_once_their_side_is_losing_and_less_when_brave(monkeypatch):
    timid = make_unit("Legionnaire Archer 1", "Enemy", 0, 0, 100, 0, [])
    timid.bravery = timid.patience = 10
    brave = make_unit("Legionnaire Shieldbearer 1", "Enemy", 1, 0, 100, 0, [])
    brave.bravery = brave.patience = 60
    marcus = make_unit("Centurion Marcus", "Enemy", 2, 0, 100, 0, [])
    other = make_unit("Legionnaire Medic 1", "Enemy", 3, 0, 100, 0, [])
    paul = make_unit("Paul", "Player", 5, 5, 200, 0, [])
    units = [timid, brave, marcus, other, paul]

    assert game_logic.flee_chance(timid, units) == 0  # nobody runs while the line holds
    game_logic.convert_unit(other, "Player", 0)
    assert game_logic.flee_chance(timid, units) > game_logic.flee_chance(brave, units)
    assert game_logic.flee_chance(marcus, units) == 0  # only Legionnaires flee
    assert game_logic.flee_chance(other, units) == 0  # nor does a convert

    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)
    assert game_logic.begin_turn(timid, units)["fled"]
    assert timid.fled and not timid.is_alive()


def test_the_battle_is_lost_the_moment_pauls_faith_hits_zero():
    paul = make_unit("Paul", "Player", 0, 0, 5, 0, [])
    peter = make_unit("Peter", "Player", 1, 0, 150, 0, [])
    legionnaire = make_unit("Legionnaire 1", "Enemy", 0, 1, 100, 0, [])
    units = [paul, peter, legionnaire]
    assert game_logic.get_winner(units) is None
    game_logic.apply_preach(legionnaire, paul)
    assert paul.faith == 0 and paul.is_alive()
    assert game_logic.get_winner(units) == "Enemy"

    peter.faith = 0  # anyone else's broken faith is Despair, not defeat
    paul.faith = 50
    assert game_logic.get_winner(units) is None


def test_converted_legionnaires_get_a_random_commoner_face_for_the_battle():
    game_logic.CONVERT_FACES_USED.clear()
    faces = game_logic.convert_face_paths()
    assert len(faces) >= 10
    converts = []
    for n in range(len(faces)):
        unit = make_unit(f"Legionnaire Archer {n + 1}", "Enemy", 0, 0, 200, 0, [])
        game_logic.convert_unit(unit, "Player", 0)
        converts.append(unit)
    assert sorted(u.face_portrait_path for u in converts) == faces  # no two alike

    first = converts[0]
    face = first.face_portrait_path
    game_logic.turn_back(first, 0)
    assert first.face_portrait_path is None
    game_logic.convert_unit(first, "Player", 0)
    assert first.face_portrait_path == face  # the same face each time

    marcus = make_unit("Centurion Marcus", "Enemy", 0, 0, 200, 0, [])
    game_logic.convert_unit(marcus, "Player", 0)
    assert marcus.face_portrait_path is None  # named enemies keep their own portrait


# --- Road to Damascus: the opening stage, and mounts ---

def test_riding_a_horse_adds_three_move_tiles():
    rider = game_logic.Unit({"name": "Rider", "team": "Player", "x": 0, "y": 0, "speed": 10, "mv": 3, "jump": 1,
                             "mp": 0, "skills": [], "color": (0, 0, 0), "mount": "horse"})
    walker = make_unit("Walker", "Player", 0, 0, 100, 0, [])
    assert rider.mv == 3 + game_logic.MOUNTS["horse"]["mv"] == 6
    assert walker.mv == 3 and not walker.mount


def test_the_road_to_damascus_is_the_first_stage_saul_and_his_guards_ride_against_six_disciples():
    assert game_logic.FIRST_STAGE_NODE == "damascus"
    manifest = load_stage_manifest()
    assert list(manifest)[0] == "damascus"
    roster = load_characters_from_csv(manifest["damascus"]["characters"])
    players = [c for c in roster if c["team"] == "Player"]
    enemies = [c for c in roster if c["team"] != "Player"]
    assert "Paul" in {c["name"] for c in players}
    assert all(c["mount"] == "horse" for c in players)
    assert len(enemies) == 6 and not any(c["mount"] for c in enemies)
    # The disciples borrow apostle tokens, so each has its own face portrait.
    assert all(os.path.exists(c["face_portrait"]) for c in enemies)


def _escape_board(monkeypatch):
    game_logic.MAP_DATA = [[0 for _ in range(8)] for _ in range(8)]
    game_logic.MAP_ROWS = game_logic.MAP_COLS = 8
    monkeypatch.setattr(game_logic, "PROP_TILES", set())
    monkeypatch.setattr(game_logic, "ESCAPE_TILES", {(7, 0), (7, 1)})
    game_logic.SKILL_REGISTRY = {"Preach": {"mp_cost": 0, "range": 1, "damage": 30, "type": "Faith"}}


def test_disciples_run_for_the_exits_and_escape_once_they_reach_one(monkeypatch):
    _escape_board(monkeypatch)
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.99)  # never stands firm
    disciple = make_unit("Ananias", "Enemy", 2, 3, 100, 0, ["Preach"], char_class="Disciple")
    saul = make_unit("Paul", "Player", 0, 7, 200, 0, [])
    units = [disciple, saul]

    plan = game_logic.plan_escape(disciple, units)
    assert plan and not plan["escapes"]
    before = game_logic.distance_to_escape((disciple.x, disciple.y))
    game_logic.carry_out_escape(disciple, plan)
    assert game_logic.distance_to_escape((disciple.x, disciple.y)) < before

    disciple.has_moved = False
    disciple.x, disciple.y = 5, 1  # an exit is within its 3 Move
    plan = game_logic.plan_escape(disciple, units)
    assert plan["escapes"]
    game_logic.carry_out_escape(disciple, plan)
    assert disciple.fled and not disciple.is_alive()
    assert game_logic.get_winner(units) == "Player"  # the last disciple got away


def test_netted_converted_or_non_disciple_units_dont_run(monkeypatch):
    _escape_board(monkeypatch)
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.99)
    netted = make_unit("Timon", "Enemy", 2, 3, 100, 0, [], char_class="Disciple")
    netted.snared_turns = 1
    convert = make_unit("Nicolas", "Enemy", 3, 3, 100, 0, [], char_class="Disciple")
    game_logic.convert_unit(convert, "Player", 0)
    soldier = make_unit("Legionnaire 1", "Enemy", 4, 3, 100, 0, [], char_class="Shieldbearer")
    units = [netted, convert, soldier]
    assert game_logic.plan_escape(netted, units) is None
    assert game_logic.plan_escape(convert, units) is None
    assert game_logic.plan_escape(soldier, units) is None


def test_the_damascus_disciples_start_in_the_centre_and_can_escape_down_the_road():
    manifest = load_stage_manifest()
    folder = os.path.dirname(manifest["damascus"]["characters"])
    exits = load_escape_tiles_from_csv(os.path.join(folder, "escape.csv"))
    assert exits
    for c in load_characters_from_csv(manifest["damascus"]["characters"]):
        if c["team"] == "Enemy":
            assert c["class"] in game_logic.ESCAPING_CLASSES
            assert 3 <= c["x"] <= 8 and 3 <= c["y"] <= 6, c["name"]  # the middle of the 12x10 map


def test_the_light_from_heaven_comes_when_two_disciples_are_left():
    scene = game_logic.STAGE_SCENES["damascus"]
    assert scene["enemies_left"] == 2
    paul = make_unit("Paul", "Player", 0, 0, 200, 0, [])
    disciples = [make_unit(f"Disciple {n}", "Enemy", n, 5, 100, 0, [], char_class="Disciple") for n in range(4)]
    units = [paul] + disciples
    assert not game_logic.scene_due("damascus", units)
    game_logic.convert_unit(disciples[0], "Player", 0)
    assert not game_logic.scene_due("damascus", units)
    disciples[1].fled = True
    game_logic.kill_unit(disciples[1])  # escaped
    assert game_logic.scene_due("damascus", units)  # two left standing
    assert not game_logic.scene_due("jerusalem", units)  # only stages with a scene

    game_logic.EFFECT_EVENTS.clear()
    game_logic.strike_down(paul)
    assert paul.fallen and paul.is_alive()
    assert game_logic.EFFECT_EVENTS[-1]["trigger"] == "@heavenly_light"


def test_the_damascus_scene_has_its_dialogue():
    lines = load_dialogues_from_csv(map_id="damascus")[game_logic.STAGE_SCENES["damascus"]["dialogue"]]
    speakers = [speaker for speaker, _ in lines]
    assert "Jesus" in speakers and "Saul" in speakers
    assert any("why are you persecuting me" in text for _, text in lines)


# --- Persecute (Saul's band on the Road to Damascus) ---

def test_persecute_takes_ten_faith_and_slows_without_stacking():
    game_logic.SKILL_REGISTRY = {"Persecute": {"mp_cost": 0, "range": 1, "damage": 0, "type": "Status"}}
    saul = make_unit("Paul", "Player", 0, 0, 200, 0, ["Persecute"])
    disciple = make_unit("Ananias", "Enemy", 0, 1, 100, 0, [], char_class="Disciple")
    game_logic.apply_skill_status("Persecute", saul, disciple, [saul, disciple])
    assert disciple.faith == 100 - game_logic.PERSECUTE_FAITH
    assert disciple.mv == 3 - game_logic.PERSECUTE_SLOW
    game_logic.apply_skill_status("Persecute", saul, disciple, [saul, disciple])
    assert disciple.mv == 3 - game_logic.PERSECUTE_SLOW  # refreshed, not stacked
    for _ in range(game_logic.PERSECUTE_TURNS + 1):
        game_logic.begin_turn(disciple)
    assert disciple.mv == 3


def test_a_disciple_persecuted_to_zero_faith_is_arrested():
    saul = make_unit("Paul", "Player", 0, 0, 200, 0, ["Persecute"])
    disciple = make_unit("Timon", "Enemy", 0, 1, game_logic.PERSECUTE_FAITH, 0, [], char_class="Disciple")
    other = make_unit("Nicolas", "Enemy", 3, 3, 100, 0, [], char_class="Disciple")
    units = [saul, disciple, other]
    game_logic.apply_skill_status("Persecute", saul, disciple, units)
    assert disciple.arrested and not disciple.is_alive()
    assert game_logic.enemies_standing(units) == [other]


def test_the_damascus_party_persecutes_instead_of_preaching():
    saul = make_unit("Paul", "Player", 0, 0, 200, 0, ["Preach", "Heal"])
    hero = make_unit("Lydia", "Player", 1, 0, 140, 0, ["Preach", "Inspire"])
    disciple = make_unit("Ananias", "Enemy", 5, 5, 100, 0, ["Preach"], char_class="Disciple")
    game_logic.apply_stage_skill_swaps("damascus", [saul, hero, disciple])
    assert saul.skills == ["Persecute", "Heal"] and hero.skills == ["Persecute", "Inspire"]
    assert disciple.skills == ["Preach"]  # the disciples still preach
    other = make_unit("Peter", "Player", 0, 0, 100, 0, ["Preach"])
    game_logic.apply_stage_skill_swaps("jerusalem", [other])
    assert other.skills == ["Preach"]

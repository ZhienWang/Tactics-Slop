import pytest

from scripts import game_logic
from scripts.data_editor import load_characters_from_csv


def make_unit(name, team="Player", char_class="Apostle", level=1):
    return game_logic.Unit({
        "name": name, "team": team, "class": char_class, "x": 0, "y": 0, "speed": 10, "mv": 3, "jump": 1,
        "faith": 100, "mp": 20, "skills": [], "color": (255, 255, 255), "portrait_path": "", "level": level,
    })


def test_every_character_starts_at_level_one():
    for row in load_characters_from_csv():
        assert game_logic.Unit(row).level == 1
        assert game_logic.Unit(row).exp == 0


def test_action_exp_is_9_to_15_and_grows_with_target_level():
    actor = make_unit("Actor", level=5)
    assert game_logic.exp_for_action(actor, make_unit("Same", level=5)) == 11
    assert game_logic.exp_for_action(actor, make_unit("Stronger", level=7)) == 13
    assert game_logic.exp_for_action(actor, make_unit("Weaker", level=3)) == 9
    assert game_logic.exp_for_action(actor, make_unit("Far stronger", level=30)) == 15
    assert game_logic.exp_for_action(actor, make_unit("Far weaker", level=1)) == 9
    gains = [game_logic.exp_for_action(actor, make_unit("T", level=lv)) for lv in range(1, 20)]
    assert gains == sorted(gains)  # never less for a stronger target
    assert min(gains) == 9 and max(gains) == 15


def test_conversion_exp_is_45_to_65():
    actor = make_unit("Paul", level=5)
    assert game_logic.exp_for_action(actor, make_unit("Same", level=5), "convert") == 55
    assert game_logic.exp_for_action(actor, make_unit("Stronger", level=8), "convert") == 61
    assert game_logic.exp_for_action(actor, make_unit("Far stronger", level=40), "convert") == 65
    assert game_logic.exp_for_action(actor, make_unit("Far weaker", level=1), "convert") == 47
    assert game_logic.exp_for_action(make_unit("Vet", level=50), make_unit("T", level=1), "convert") == 45


def test_converting_preach_grants_conversion_exp(monkeypatch):
    paul = make_unit("Paul", char_class="Missionary")
    judas = make_unit("Judas", team="Enemy")
    judas.faith = game_logic.FAITH_CAP - 1
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)

    game_logic.resolve_faith_attack(paul, judas)

    assert judas.team == "Player"
    assert paul.exp == 55
    assert paul.exp_popup["amount"] == 55


def test_one_hundred_exp_is_a_level_and_the_rest_carries_over():
    unit = make_unit("Peter")
    assert game_logic.gain_exp(unit, 95) == 0
    assert (unit.level, unit.exp) == (1, 95)
    assert game_logic.gain_exp(unit, 12) == 1
    assert (unit.level, unit.exp) == (2, 7)
    assert game_logic.gain_exp(unit, 250) == 2
    assert (unit.level, unit.exp) == (4, 57)


def test_levels_cap_at_99():
    unit = make_unit("Methuselah", level=98)
    unit.exp = 90
    game_logic.gain_exp(unit, 500)
    assert unit.level == game_logic.MAX_LEVEL
    assert unit.exp < game_logic.EXP_PER_LEVEL


def test_level_up_grows_stats_by_job():
    apostle = make_unit("Mark")
    before = (apostle.max_mp, apostle.mp, apostle.magic_attack, apostle.magic_defense, apostle.speed)
    game_logic.gain_exp(apostle, 100)
    growth = game_logic.LEVEL_GROWTH["Apostle"]
    assert apostle.max_mp == before[0] + growth["max_mp"]
    assert apostle.mp == before[1] + growth["max_mp"]
    assert apostle.magic_attack == before[2] + growth["magic_attack"]
    assert apostle.magic_defense == before[3] + growth["magic_defense"]
    assert apostle.speed == before[4]  # speed only grows every 5th level
    game_logic.gain_exp(apostle, 300)  # to Lv 5
    assert apostle.speed == before[4] + 1


def test_rebuilt_unit_matches_one_that_levelled_up_in_battle():
    grown = make_unit("Paul", char_class="Missionary")
    game_logic.gain_exp(grown, 730)  # Lv 8
    rebuilt = make_unit("Paul", char_class="Missionary", level=grown.level)
    game_logic.apply_level_bonuses(rebuilt)
    for stat in ("max_mp", "magic_attack", "magic_defense", "speed"):
        assert getattr(rebuilt, stat) == getattr(grown, stat), stat


def test_actions_award_exp_once(monkeypatch):
    game_logic.EFFECT_EVENTS.clear()
    paul = make_unit("Paul", char_class="Missionary")
    judas = make_unit("Judas", team="Enemy", level=3)
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)
    game_logic.resolve_faith_attack(paul, judas)  # hit: goes through apply_preach
    assert paul.exp == 13
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.999)
    game_logic.resolve_faith_attack(paul, judas)  # a miss still teaches, as in FFT
    assert paul.exp == 26


def test_level_up_shows_popup_and_effect():
    game_logic.EFFECT_EVENTS.clear()
    paul = make_unit("Paul")
    paul.exp = 95
    game_logic.award_action_exp(paul, make_unit("Target"))
    assert paul.level == 2
    assert paul.exp_popup["levels"] == 1
    assert any(e["trigger"] == "@level_up" for e in game_logic.EFFECT_EVENTS)


def test_acts_and_buffs_announce_their_name_before_a_level_up(monkeypatch):
    game_logic.SKILL_BANNERS.clear()
    paul = make_unit("Paul", char_class="Missionary")
    paul.exp = 95
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)
    game_logic.resolve_faith_attack(paul, make_unit("Judas", team="Enemy"))
    assert [b["name"] for b in game_logic.SKILL_BANNERS] == ["Preach", "Level Up!"]
    assert game_logic.SKILL_BANNERS[0]["unit"] == "Paul"

    game_logic.SKILL_BANNERS.clear()
    assert game_logic.apply_morale_buff(make_unit("Mark"))
    assert [b["name"] for b in game_logic.SKILL_BANNERS] == ["Morale Surge"]

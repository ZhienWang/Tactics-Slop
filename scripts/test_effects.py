import pygame
import pytest

from scripts import game_logic
from scripts.data_editor import (
    EFFECT_ANCHORS,
    EFFECT_OUTCOMES,
    load_effects_from_csv,
    load_items_from_csv,
    load_skill_effects_from_csv,
    load_skills_from_csv,
)
from scripts.effects import PATTERNS, SHAPES, EffectManager, EffectSpec

EFFECT_EVENTS_KNOWN = {"@morale", "@rekindle", "@lead_fade", "@despair_turn", "@stunned", "@snared", "@level_up", "@disarmed", "@turned_back", "@fled", "@escaped", "@heavenly_light", "@arrested"}


@pytest.fixture(scope="module")
def specs():
    return {name: EffectSpec(row) for name, row in load_effects_from_csv().items()}


# --- effects.csv ---

def test_library_has_at_least_fifty_effects(specs):
    assert len(specs) >= 50


def test_library_has_no_offensive_category(specs):
    assert {s.category for s in specs.values()} <= {"buff", "curse", "holy", "first_aid", "flash"}


def test_every_effect_uses_a_known_pattern_shape_and_colors(specs):
    for spec in specs.values():
        assert spec.pattern in PATTERNS, spec.name
        assert spec.shape in SHAPES, spec.name
        assert spec.colors, spec.name
        assert spec.duration > 0, spec.name


def test_every_effect_lasts_at_least_three_seconds(specs):
    for spec in specs.values():
        assert spec.duration >= 3000, spec.name


def test_long_effects_stay_lively_to_the_end(specs):
    """Particles are released across the whole effect, not just its start:
    something is still visible in the last second of every effect."""
    from scripts.effects import Effect
    import random
    for spec in specs.values():
        effect = Effect(spec, (0, 0), random.Random(1))
        late = effect.duration - 1.0
        assert any(p.delay <= late + 0.9 and p.delay + p.life >= late for p in effect.particles), spec.name


def test_every_layer_names_a_real_effect(specs):
    for spec in specs.values():
        for layer in spec.layers:
            assert layer in specs, f"{spec.name} layers unknown effect {layer!r}"
            assert layer != spec.name


def test_every_effect_plays_through_without_error(specs):
    pygame.init()
    surface = pygame.Surface((400, 300))
    manager = EffectManager(specs, seed=3)
    for name in specs:
        manager.play(name, (0, 0))
    # Step through ~5 seconds of animation at 30 fps.
    for frame in range(150):
        manager.draw(surface, lambda tile: (200, 200), 1.5, now=frame * 33)
    assert not manager.active  # every effect finishes on its own


# --- skill_effects.csv ---

def test_every_binding_names_a_real_effect_and_trigger(specs):
    skills = load_skills_from_csv()
    items = load_items_from_csv()
    for trigger, bindings in load_skill_effects_from_csv().items():
        assert trigger in skills or trigger in items or trigger in EFFECT_EVENTS_KNOWN, trigger
        for binding in bindings:
            assert binding["effect"] in specs, f"{trigger} binds unknown effect {binding['effect']!r}"
            assert binding["anchor"] in EFFECT_ANCHORS
            assert binding["on"] in EFFECT_OUTCOMES


def test_offensive_skills_only_show_the_defenders_block():
    """No attack effects: a lethal Physical skill (Shoot) may only bind an
    effect for when a guard blocks it - the defender's protective flare.
    Slash no longer wounds - it disarms - so its seal effect is allowed."""
    bindings = load_skill_effects_from_csv()
    skills = load_skills_from_csv()
    for trigger, rows in bindings.items():
        if trigger in game_logic.DISARM_SKILLS:
            continue
        if trigger in skills and skills[trigger]["type"] == "Physical":
            for row in rows:
                assert row["on"] == "blocked" and row["anchor"] == "target", f"{trigger} binds an attack effect"


def test_guarded_block_reports_blocked():
    game_logic.EFFECT_EVENTS.clear()
    game_logic.MAP_DATA = [[0] * 4 for _ in range(4)]
    attacker = make_unit("Legionnaire", "Enemy", 0, 0, 50)
    peter = make_unit("Peter", "Player", 0, 1, 50)
    peter.guarded = True
    game_logic.random.seed(0)
    original = game_logic.random.random
    game_logic.random.random = lambda: 0.0  # always within hit chance
    try:
        game_logic.resolve_physical_hit(attacker, peter, "Slash")
    finally:
        game_logic.random.random = original
    assert game_logic.EFFECT_EVENTS[-1]["outcome"] == "blocked"


def test_most_of_the_library_is_bound(specs):
    """Everything bound, directly or as a layer of something bound."""
    used = set()

    def add(name):
        if name in used:
            return
        used.add(name)
        for layer in specs[name].layers:
            add(layer)

    for rows in load_skill_effects_from_csv().values():
        for row in rows:
            add(row["effect"])
    assert len(used) >= 45


# --- rules report outcomes ---

def make_unit(name, team, x, y, faith):
    return game_logic.Unit({
        "name": name, "team": team, "class": "Knight", "x": x, "y": y, "speed": 10, "mv": 3, "jump": 1,
        "faith": faith, "mp": 50, "skills": [], "color": (255, 255, 255), "portrait_path": "",
    })


def test_preach_reports_hit_convert_and_shaken():
    game_logic.EFFECT_EVENTS.clear()
    paul = make_unit("Paul", "Player", 0, 0, 100)
    judas = make_unit("Judas", "Enemy", 0, 1, 40)
    game_logic.apply_preach(paul, judas, "Preach")
    judas.faith = game_logic.FAITH_CAP - 1
    game_logic.apply_preach(paul, judas, "Preach")
    legionnaire = make_unit("Legionnaire", "Enemy", 1, 0, 10)
    peter = make_unit("Peter", "Player", 1, 1, 150)
    game_logic.apply_preach(legionnaire, peter, "Preach")

    outcomes = [e["outcome"] for e in game_logic.EFFECT_EVENTS]
    assert outcomes == ["hit", "convert", "shaken"]
    assert game_logic.EFFECT_EVENTS[0]["target"] == (0, 1)


def test_lead_reports_every_recipient():
    game_logic.EFFECT_EVENTS.clear()
    paul = make_unit("Paul", "Player", 2, 2, 100)
    near = make_unit("Near", "Player", 3, 2, 100)
    far = make_unit("Far", "Player", 6, 6, 100)
    game_logic.apply_skill_status("Lead", paul, paul, [paul, near, far])

    event = game_logic.EFFECT_EVENTS[-1]
    assert event["trigger"] == "Lead"
    assert sorted(event["recipients"]) == [(2, 2), (3, 2)]


def test_queued_events_play_their_bound_effects(specs):
    game_logic.EFFECT_EVENTS.clear()
    manager = EffectManager(specs, seed=1)
    paul = make_unit("Paul", "Player", 0, 0, 100)
    judas = make_unit("Judas", "Enemy", 0, 1, 40)
    game_logic.queue_effect("Preach", paul, judas, "hit")
    game_logic.queue_effect("Preach", paul, judas, "miss")

    game_logic.play_queued_effects(manager, {"Preach": [
        {"effect": "holy_motes", "anchor": "target", "on": "hit"},
        {"effect": "fizzle", "anchor": "caster", "on": "miss"},
    ]})

    assert [(e.spec.name, e.tile) for e in manager.effects] == [("holy_motes", (0, 1)), ("fizzle", (0, 0))]
    assert not game_logic.EFFECT_EVENTS

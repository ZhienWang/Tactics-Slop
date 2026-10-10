import random

import pygame
import pytest

from scripts import hero_look as hl
from scripts.assets import load_image_safe
from scripts.hero import hero_character


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.display.init()
    pygame.display.set_mode((1, 1))


def test_every_uniform_only_uses_real_figure_options():
    for name, uniform in hl.UNIFORMS.items():
        for key, value in uniform.items():
            if key in hl.fb.OPTIONS:
                assert value in hl.fb.OPTIONS[key], (name, key, value)
        assert uniform["blurb"]
        # A book needs both hands - no weapon with it.
        assert not (uniform["arms"] == "book" and uniform["weapon"] != "none"), name


@pytest.mark.parametrize("uniform", list(hl.UNIFORMS))
def test_every_uniform_draws_as_a_full_size_token(uniform):
    look = {**hl.default_look("Sentinel"), "uniform": uniform}
    token = hl.render_look(look)
    assert token.get_size() == hl.TOKEN_SIZE
    assert token.get_bounding_rect().height > 100   # there's a figure on it


def test_the_default_look_wears_the_roles_colour():
    assert hl.default_look("Analyst")["main"] == "purple"
    assert hl.look_spec(hl.default_look("Explorer"))["main"] == "gold"


def test_random_looks_are_valid_and_feminine_ones_are_beardless():
    rng = random.Random(4)
    for _ in range(30):
        look = hl.random_look(rng)
        for key, values in hl.OPTIONS.items():
            assert look[key] in values, key
        if look["feminine"]:
            assert look["beard"] == "none"


def test_a_custom_hero_token_loads_by_path_like_any_other_art():
    profile = {"name": "Tester", "type": "ISTJ", "look": hl.default_look("Sentinel")}
    path = hl.hero_token(profile, "Sentinel")
    assert path.startswith("hero_look/")
    assert load_image_safe(path).get_size() == hl.TOKEN_SIZE
    assert hl.hero_token({"name": "Old save", "type": "ISTJ"}, "Sentinel") == "assets/characters/hero_sentinel.png"


def test_the_hero_fights_in_their_own_look():
    profile = {"name": "Tester", "type": "ISTJ", "look": hl.default_look("Sentinel")}
    roster = [{"name": "Paul", "team": "Player", "x": 1, "y": 1}]
    entry = hero_character(profile, roster, [[0] * 4 for _ in range(4)], set())
    assert entry["portrait_path"] == hl.look_key(profile["look"])
    assert entry["face_portrait"] == ""

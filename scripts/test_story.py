"""Tests for the visual-novel scenes (scripts/story.py): the story data is
well formed, every story reaches its closing Scripture card, and the player
walks the script the way the scene format says."""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from scripts import story
from scripts.data_editor import load_world_map_nodes
from scripts.skybox import SKY_PROFILES


@pytest.fixture(scope="module")
def surface():
    pygame.init()
    yield pygame.display.set_mode((story.SCREEN_WIDTH, story.SCREEN_HEIGHT))


def test_every_row_uses_a_known_command():
    for scene, rows in story.load_story().items():
        for row in rows:
            assert row["command"] in story.COMMANDS, f"{scene}: unknown command {row['command']!r}"


def test_show_rows_name_a_real_slot():
    for scene, rows in story.load_story().items():
        for row in rows:
            if row["command"] == "show":
                assert row["text"] in story.SLOTS, f"{scene}: {row['who']} shown at {row['text']!r}"


def test_procedural_backdrops_name_a_real_sky_and_ground():
    for scene, rows in story.load_story().items():
        for row in rows:
            if row["command"] == "bg" and "/" in row["text"]:
                sky, ground = row["text"].split("/")
                assert sky in SKY_PROFILES, f"{scene}: unknown sky {sky!r}"
                assert story.ground_texture_path(ground), f"{scene}: no assets/{ground}.png or .jpg"


def test_branch_rows_follow_a_choice_with_that_many_options():
    for scene, rows in story.load_story().items():
        options = 0
        for row in rows:
            if row["command"] == "choice":
                options = len(row["text"].split("|"))
            if row["when"]:
                assert options, f"{scene}: a `when` row before any choice"
                assert 1 <= int(row["when"]) <= options, f"{scene}: when={row['when']} but the choice has {options} options"


def test_every_chapter_is_on_the_world_map_and_has_a_scene():
    nodes, _ = load_world_map_nodes()
    scenes = story.load_story()
    for chapter in story.load_chapters():
        assert chapter["node_id"] in nodes, f"chapter {chapter['chapter']} is at unknown node {chapter['node_id']!r}"
        assert any(s in scenes for s in story.scene_ids(chapter["node_id"])), f"chapter {chapter['chapter']} has no scene"


def test_every_story_ends_by_sending_players_to_scripture():
    """GamePlan principle 3: each story ends on its passage and questions."""
    scenes = story.load_story()
    for chapter in story.load_chapters():
        intro, outro = story.scene_ids(chapter["node_id"])
        last = scenes.get(outro) or scenes[intro]
        assert last[-1]["command"] == "reflect", f"{chapter['title']} doesn't end on a reflect card"


ROWS = [
    {"command": "bg", "who": "", "text": "night/stone", "when": ""},
    {"command": "show", "who": "Saul", "text": "left", "when": ""},
    {"command": "say", "who": "Saul", "text": "Well, {hero}?", "when": ""},
    {"command": "choice", "who": "Answer?", "text": "Yes|No", "when": ""},
    {"command": "say", "who": "Saul", "text": "Good.", "when": "1"},
    {"command": "say", "who": "Saul", "text": "Pity.", "when": "2"},
    {"command": "hide", "who": "", "text": "", "when": ""},
    {"command": "reflect", "who": "Acts 9", "text": "Q1|Q2", "when": ""},
]


def test_player_applies_instant_rows_and_fills_in_the_hero(surface):
    player = story.StoryPlayer(surface, ROWS, hero_name="Lydia")
    step = player.next_step()
    assert step["command"] == "say" and step["text"] == "Well, Lydia?"
    assert player.backdrop is not None
    assert [c["name"] for c in player.cast] == ["Saul"]


def test_player_only_plays_the_chosen_branch(surface):
    player = story.StoryPlayer(surface, ROWS)
    player.step = player.next_step()
    player.step["typed"] = True
    player.advance()
    assert player.step["command"] == "choice"
    player.choose(1)  # "No"
    assert player.step["text"] == "Pity."
    player.advance()  # the first press finishes the typing line...
    assert player.step["text"] == "Pity."
    player.advance()  # ...the second moves on
    assert player.step["command"] == "reflect" and player.cast == []


def test_skip_stops_at_choices_and_the_closing_card(surface):
    player = story.StoryPlayer(surface, ROWS)
    player.step = player.next_step()
    player.skip()
    assert player.step["command"] == "choice"
    player.choose(0)
    player.skip()
    assert player.step["command"] == "reflect"
    assert ("Saul", "Good.") in player.log


def test_every_scene_draws(surface):
    """Each scene renders every step without error (a smoke test of the art
    lookups: backdrops, portraits, light figures)."""
    for scene, rows in story.load_story().items():
        player = story.StoryPlayer(surface, rows, hero_name="Theophilus", seed=scene)
        player.step = player.next_step()
        while player.step is not None:
            player.draw()
            if player.step["command"] == "choice":
                player.choose(0)
            else:
                player.step = player.next_step()

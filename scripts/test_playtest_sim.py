"""Keeps tools/playtest_sim.py in step with the game: if the battle rules
change in a way the simulator no longer understands, this fails."""
import importlib.util
import os

from scripts import game_logic

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_sim():
    spec = importlib.util.spec_from_file_location("playtest_sim", os.path.join(ROOT, "tools", "playtest_sim.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_simulator_plays_a_battle_on_every_stage():
    sim = load_sim()
    manifest = sim.load_stage_manifest()
    with sim.player_policy("human"):
        for node, stage in manifest.items():
            winner, turns, stats = sim.run_battle(stage, seed=0, max_turns=60)
            assert winner in ("Player", "Enemy", "timeout"), node
            assert turns > 0, node
            assert stats["party_size"] > 0, node


def test_importing_the_simulator_leaves_the_game_ai_alone():
    original = game_logic.score_ai_candidate
    sim = load_sim()
    assert game_logic.score_ai_candidate is original
    with sim.player_policy("human"):
        assert game_logic.score_ai_candidate is not original
    assert game_logic.score_ai_candidate is original  # restored afterwards

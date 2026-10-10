"""Editable anime choices, saved exports and original terrain loading."""
import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
from tools import character_generator as generator
from scripts.assets import cache_terrain_images


def test_original_controls_render_and_each_choice_changes_art():
    assert set(generator.ROWS) == set(generator.fb.OPTIONS)
    for key, values in generator.OPTIONS.items():
        base = {**generator.DEFAULT_SPEC, "arms":"hold", "cape":"long", "legs":"trousers"}
        if key == "hair_color":
            base["hair"] = "standard"
        signatures = set()
        for value in values:
            image = generator.render_surface({**base,key:value},2)
            assert image.get_size() == (340,170)
            assert image.get_bounding_rect(min_alpha=32).height > 0
            signatures.add(pygame.image.tobytes(image,"RGBA"))
        assert len(signatures) == len(values), key


def test_save_exports_preview_and_matching_portrait(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "ROOT", str(tmp_path))
    out = tmp_path / "assets" / "anime" / "units"
    monkeypatch.setattr(generator, "OUT_DIR", str(out))
    monkeypatch.setattr(generator, "DESIGNS_PATH", str(tmp_path / "designs.json"))
    spec = {**generator.DEFAULT_SPEC,"feminine":True,"hair":"long","legs":"trousers"}
    path = generator.save_design("Test Artist", "Person", spec)
    saved = pygame.image.load(str(tmp_path / path))
    preview = generator.art.figure(spec)
    assert saved.get_size() == preview.get_size()
    assert pygame.image.tobytes(saved,"RGBA") == pygame.image.tobytes(preview,"RGBA")
    assert (tmp_path / "assets/anime/portraits/test_artist.png").exists()
    design = json.loads((tmp_path / "designs.json").read_text())["test_artist"]
    assert design["spec"] == spec and design["art_style"] == "painted_parts"


def test_selection_randomize_and_saved_design_reload(tmp_path, monkeypatch):
    monkeypatch.setattr(generator,"DESIGNS_PATH",str(tmp_path/"designs.json"))
    gen = generator.Generator()
    gen.step("head",1)
    assert gen.spec["head"] == "oval"
    gen.randomize("enemy")
    assert gen.spec["body"] == "armor" and set(gen.spec) == set(generator.OPTIONS)
    gen.randomize("person")
    assert set(gen.spec) == set(generator.OPTIONS)
    spec = {**generator.DEFAULT_SPEC,"head":"wide","arms":"raised","legs":"trousers"}
    gen.designs={"test":{"name":"Test", "team":"Person", "spec":spec}}
    gen.load_selected()
    assert gen.name == "Test" and gen.spec == spec


def test_terrain_uses_original_path(monkeypatch):
    from scripts import assets
    calls = []
    monkeypatch.setattr(assets, "load_image_safe", lambda path, errors: calls.append(path) or path)
    paths = ["assets/moss.png", "assets/stone.png"]
    cache_terrain_images([paths, paths], [])
    assert calls == paths

"""The character generator's figure builder (assets/figure_builder.py):
every part option, and random designs, must build and render."""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"))

import figure_builder as fb  # noqa: E402


def test_every_option_of_every_part_builds():
    for key, values in fb.OPTIONS.items():
        for value in values:
            svg = fb.figure_svg({**fb.DEFAULT_SPEC, key: value, "arms": "hold"})
            assert svg.startswith("<svg") and svg.endswith("</svg>"), (key, value)


def test_random_people_and_enemies_build_and_render_at_token_size():
    rng = random.Random(1)
    for kind in ("person", "enemy"):
        for _ in range(10):
            spec = fb.random_spec(kind, rng)
            assert set(fb.OPTIONS) <= set(spec)
            assert fb.figure_svg(spec).startswith("<svg")
    width, height, data = fb.render_rgba(fb.random_spec("enemy", rng), scale=2)
    assert (width, height) == (340, 170)  # the same size as every unit token
    assert len(data) == width * height * 4

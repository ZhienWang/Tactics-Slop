import csv
import os
import re

import pygame
import pytest

from scripts.data_editor import DATA_DIR, VOICE_DIR, load_voice_cast_from_csv, voice_clip_id
from scripts.voices import MUSIC_DUCKED_VOLUME, MUSIC_VOLUME, DialogueVoice

ROOT = os.path.dirname(DATA_DIR)


def dialogue_rows():
    with open(os.path.join(DATA_DIR, "dialogues.csv"), newline="", encoding="utf-8") as f:
        return [(r["character"].strip(), r["text"].strip()) for r in csv.DictReader(f)]


def test_every_dialogue_line_has_a_voice_clip():
    missing = [f"{speaker}: {text[:40]}" for speaker, text in dialogue_rows()
               if not os.path.exists(os.path.join(ROOT, VOICE_DIR, f"{voice_clip_id(speaker, text)}.ogg"))]
    assert not missing, "run tools/generate_voices.py - no clip for:\n" + "\n".join(missing)


def test_every_speaker_is_cast():
    cast = load_voice_cast_from_csv()
    assert "*" in cast
    for speaker, _ in dialogue_rows():
        assert speaker in cast, f"{speaker} has no voice in data/voices.csv (would fall back to '*')"


def test_cast_rates_and_pitches_are_well_formed():
    for character, voice in load_voice_cast_from_csv().items():
        assert re.fullmatch(r"[+-]\d+%", voice["rate"]), character
        assert re.fullmatch(r"[+-]\d+Hz", voice["pitch"]), character
        assert voice["voice"].endswith("Neural"), character


def test_clip_id_changes_with_the_text_but_not_whitespace():
    assert voice_clip_id("Paul", "Grace to you.") == voice_clip_id(" Paul ", "Grace to you. ")
    assert voice_clip_id("Paul", "Grace to you.") != voice_clip_id("Paul", "Peace to you.")
    assert voice_clip_id("Paul", "Amen.") != voice_clip_id("Peter", "Amen.")


@pytest.fixture
def mixer():
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.mixer.init()
    yield
    pygame.mixer.quit()


def test_voice_plays_switches_and_stops(mixer):
    first, second = dialogue_rows()[:2]
    voice = DialogueVoice()

    voice.update(first)
    assert voice.speaking
    assert pygame.mixer.music.get_volume() == pytest.approx(MUSIC_DUCKED_VOLUME, abs=0.01)

    voice.update(second)  # advancing the dialogue cuts the previous line off
    busy = [i for i in range(pygame.mixer.get_num_channels()) if pygame.mixer.Channel(i).get_busy()]
    assert len(busy) == 1  # only the new line is playing
    assert voice.speaking

    voice.update(None)  # dialogue closed
    assert not voice.speaking
    voice.update(None)
    assert pygame.mixer.music.get_volume() == pytest.approx(MUSIC_VOLUME, abs=0.01)


def test_line_without_a_clip_is_silent(mixer):
    voice = DialogueVoice()
    voice.update(("Nobody", "This line was never recorded."))
    assert not voice.speaking

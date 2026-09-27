"""Spoken dialogue: plays each dialogue line's voice clip while it's on
screen. Clips are made by tools/generate_voices.py (cast in
data/voices.csv) and named by scripts.data_editor.voice_clip_id; a line
without a clip is simply silent.

The battle calls DialogueVoice.update() every frame with whichever line is
showing (or None). A new line stops the previous clip and starts its own;
closing the dialogue stops it. Background music is lowered while someone is
speaking and brought back up afterwards.
"""
import os

import pygame

from scripts.data_editor import VOICE_DIR, voice_clip_id

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE_VOLUME = 1.0
MUSIC_VOLUME = 0.5
MUSIC_DUCKED_VOLUME = 0.18


class DialogueVoice:
    def __init__(self, voice_dir=None):
        self.voice_dir = voice_dir or os.path.join(ROOT, VOICE_DIR)
        self.current_line = None
        self.channel = None
        self.ducked = False

    def clip_path(self, speaker, text):
        return os.path.join(self.voice_dir, f"{voice_clip_id(speaker, text)}.ogg")

    def update(self, line):
        """`line` is the (speaker, text) on screen, or None for no dialogue."""
        if line != self.current_line:
            self.stop()
            self.current_line = line
            if line is not None:
                self._play(*line)
        if self.ducked and not self.speaking:
            self._set_music(MUSIC_VOLUME)
            self.ducked = False

    @property
    def speaking(self):
        return self.channel is not None and self.channel.get_busy()

    def _play(self, speaker, text):
        path = self.clip_path(speaker, text)
        if not os.path.exists(path) or not pygame.mixer.get_init():
            return
        try:
            sound = pygame.mixer.Sound(path)
        except (pygame.error, OSError):
            return
        sound.set_volume(VOICE_VOLUME)
        self.channel = sound.play()
        if self.channel is not None:
            self._set_music(MUSIC_DUCKED_VOLUME)
            self.ducked = True

    def stop(self):
        if self.channel is not None:
            self.channel.stop()
            self.channel = None

    @staticmethod
    def _set_music(volume):
        if pygame.mixer.get_init():
            pygame.mixer.music.set_volume(volume)

"""Composes the world map's theme: assets/world_theme.ogg.

A short, light-hearted folk tune in F major - a plucked, lyre-like lead over
an oom-pah bass, offbeat chord strums, a frame drum and a tambourine - in
an A A B A form of 32 bars that loops seamlessly (the ringing tail of the
last bar is folded back over the first). Everything is synthesized here
with numpy, so there's no sample library or licence to worry about; the
plucked strings use Karplus-Strong synthesis.

Needs numpy and imageio-ffmpeg (to encode the .ogg).
Run from the project root:   python tools/generate_world_music.py
"""
import os
import subprocess
import sys
import tempfile
import wave

import imageio_ffmpeg
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(ROOT, "assets", "world_theme.ogg")

RATE = 44100
BPM = 116
BEAT = 60 / BPM
BAR = 4 * BEAT
TAIL = 3.0          # seconds of ring-out folded back onto the start
rng = np.random.default_rng(7)

# MIDI note numbers, F major.
F3, G3, A3, Bb3, C4, D4, E4, F4, G4, A4, Bb4, C5, D5, E5, F5, G5, A5, Bb5 = (
    53, 55, 57, 58, 60, 62, 64, 65, 67, 69, 70, 72, 74, 76, 77, 79, 81, 82)
R = None  # a rest

# Chords per half bar: (root, third, fifth).
F, Dm, Bb, C, Gm = (F3, A3, C4), (D4 - 12, F3, A3), (Bb3 - 12, D4 - 12, F3), (C4 - 12, E4 - 12, G3), (G3 - 12, Bb3 - 12, D4 - 12)
A_CHORDS = [F, F, Dm, Dm, Bb, Bb, C, C, F, F, Dm, Dm, Bb, C, F, F]
B_CHORDS = [Bb, Bb, F, F, Gm, Gm, C, C, Bb, Bb, F, F, Gm, C, F, F]

# The tune, bar by bar: (note, beats).
A_TUNE = [
    [(C5, .5), (A4, .5), (C5, .5), (F5, .5), (E5, .5), (D5, .5), (C5, 1)],
    [(D5, .5), (F5, .5), (A4, 1), (D5, .5), (C5, .5), (A4, 1)],
    [(Bb4, .5), (D5, .5), (F5, .5), (D5, .5), (C5, .5), (Bb4, .5), (A4, 1)],
    [(G4, .5), (A4, .5), (Bb4, .5), (C5, .5), (E5, 1.5), (R, .5)],
    [(C5, .5), (A4, .5), (C5, .5), (F5, .5), (A5, 1), (G5, .5), (F5, .5)],
    [(E5, .5), (D5, .5), (F5, 1), (A4, 1), (R, 1)],
    [(D5, .5), (Bb4, .5), (D5, .5), (F5, .5), (E5, .5), (C5, .5), (D5, .5), (E5, .5)],
    [(F5, 1.5), (C5, .5), (F4, 1), (R, 1)],
]
B_TUNE = [
    [(F5, .5), (F5, .5), (D5, .5), (F5, .5), (G5, 1), (F5, 1)],
    [(A5, .5), (G5, .5), (F5, .5), (C5, .5), (A4, 1), (C5, 1)],
    [(Bb4, .5), (D5, .5), (G5, .5), (F5, .5), (D5, .5), (Bb4, .5), (G4, 1)],
    [(C5, .5), (E5, .5), (G5, .5), (Bb5, .5), (A5, .5), (G5, .5), (E5, 1)],
    [(D5, .5), (F5, .5), (Bb5, 1), (A5, .5), (G5, .5), (F5, 1)],
    [(C5, .5), (F5, .5), (A5, 1), (G5, .5), (F5, .5), (C5, 1)],
    [(Bb4, .5), (D5, .5), (G5, .5), (F5, .5), (E5, .5), (G5, .5), (C5, 1)],
    [(F5, 2), (R, 2)],
]
FORM = [("A", A_TUNE, A_CHORDS), ("A", A_TUNE, A_CHORDS), ("B", B_TUNE, B_CHORDS), ("A", A_TUNE, A_CHORDS)]


def freq(note):
    return 440.0 * 2 ** ((note - 69) / 12)


def pluck(note, seconds, brightness=0.5, decay=0.996):
    """A Karplus-Strong plucked string: a burst of noise fed round a delay
    line one period long, averaged (softened) a little each pass."""
    n = int(seconds * RATE)
    period = max(2, int(round(RATE / freq(note))))
    out = np.zeros(n + period + 1)
    burst = rng.uniform(-1, 1, period)
    # Smooth the burst for a rounder, less wiry tone.
    burst = np.convolve(burst, np.ones(3) / 3, mode="same") * (1 - brightness) + burst * brightness
    out[:period] = burst
    for start in range(period, n + period + 1, period):
        end = min(start + period, n + period + 1)
        prev = out[start - period:end - period]
        prev_shift = out[start - period - 1:end - period - 1] if start - period - 1 >= 0 else np.concatenate(([0.0], prev[:-1]))
        out[start:end] = decay * 0.5 * (prev + prev_shift[:len(prev)])
    out = out[:n]
    fade = np.minimum(1, np.linspace(n / (RATE * 0.02), 0, n))  # a short release at the end
    return out * fade


def body(note, seconds, level=0.35):
    """A soft sine under the pluck, so the lead has some warmth."""
    t = np.arange(int(seconds * RATE)) / RATE
    env = np.exp(-t * 3.2) * np.minimum(1, t * 200)
    return level * env * (np.sin(2 * np.pi * freq(note) * t) + 0.2 * np.sin(4 * np.pi * freq(note) * t))


def frame_drum(seconds=0.35):
    t = np.arange(int(seconds * RATE)) / RATE
    pitch = 95 * np.exp(-t * 9) + 55
    phase = 2 * np.pi * np.cumsum(pitch) / RATE
    return np.sin(phase) * np.exp(-t * 11)


def tambourine(seconds=0.12, accent=1.0):
    t = np.arange(int(seconds * RATE)) / RATE
    noise = rng.uniform(-1, 1, len(t))
    noise = noise - np.concatenate(([0], noise[:-1]))       # tilt it bright
    jingle = np.sin(2 * np.pi * 6200 * t) * 0.3 + np.sin(2 * np.pi * 8100 * t) * 0.2
    return (noise * 0.6 + jingle) * np.exp(-t * 38) * accent


def add(track, sound, at, gain=1.0, pan=0.0):
    """Mixes a mono sound into the stereo track at `at` seconds."""
    i = int(at * RATE)
    sound = sound[:max(0, track.shape[0] - i)]
    left, right = np.sqrt((1 - pan) / 2), np.sqrt((1 + pan) / 2)
    track[i:i + len(sound), 0] += sound * gain * left
    track[i:i + len(sound), 1] += sound * gain * right


def compose():
    bars = sum(len(tune) for _, tune, _ in FORM)
    length = bars * BAR
    track = np.zeros((int((length + TAIL) * RATE), 2))
    bar_index = 0
    for section, (name, tune, chords) in enumerate(FORM):
        last = section == len(FORM) - 1
        for bar, notes in enumerate(tune):
            start = bar_index * BAR
            # The tune: plucked lead with a soft body, a little left of centre.
            t = start
            for note, beats in notes:
                if note is not None:
                    ring = max(beats * BEAT * 2.2, 0.6)
                    add(track, pluck(note, ring, brightness=0.55, decay=0.997), t, 0.42, pan=-0.15)
                    add(track, body(note, ring), t, 0.32, pan=-0.15)
                    if last and (t - start) == 0:
                        # A glockenspiel ping an octave up, for the last time round.
                        add(track, body(note + 12, 0.8, level=0.5), t, 0.18, pan=0.3)
                t += beats * BEAT
            # Oom-pah: bass on 1 and 3, chord strums on 2 and 4.
            for half in (0, 1):
                root, third, fifth = chords[bar * 2 + half]
                beat_one = start + half * 2 * BEAT
                bass = root - 12 if half == 0 else fifth - 12
                add(track, pluck(bass, BEAT * 1.6, brightness=0.2, decay=0.995), beat_one, 0.55)
                for k, note in enumerate((root + 12, third + 12, fifth + 12)):
                    add(track, pluck(note, BEAT * 0.7, brightness=0.35, decay=0.99), beat_one + BEAT + k * 0.012, 0.16, pan=0.35)
            # Percussion: frame drum on 1 and 3, tambourine on the eighths.
            for beat in range(4):
                if beat in (0, 2):
                    add(track, frame_drum(), start + beat * BEAT, 0.35)
                for eighth in (0, 1):
                    accent = 1.0 if (beat in (1, 3) and eighth == 0) else 0.45
                    add(track, tambourine(accent=accent), start + (beat + eighth * 0.5) * BEAT + rng.uniform(0, 0.006),
                        0.06, pan=0.4)
            bar_index += 1
    # A touch of room: a couple of quiet echoes.
    room = track.copy()
    for delay, gain in ((0.083, 0.18), (0.131, 0.12), (0.197, 0.08)):
        d = int(delay * RATE)
        room[d:] += track[:-d] * gain
    track = room
    # Fold the ring-out back over the start so the loop is seamless.
    n = int(length * RATE)
    track[:track.shape[0] - n] += track[n:]
    track = track[:n]
    track /= np.max(np.abs(track)) * 1.12
    return track


def main():
    track = compose()
    pcm = (track * 32767).astype(np.int16)
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = os.path.join(tmp, "world_theme.wav")
        with wave.open(wav_path, "wb") as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(RATE)
            f.writeframes(pcm.tobytes())
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", wav_path,
                        "-c:a", "libvorbis", "-q:a", "4", OUT_PATH], check=True)
    print(f"wrote {os.path.relpath(OUT_PATH, ROOT)} ({len(track) / RATE:.0f}s loop)")


if __name__ == "__main__":
    sys.exit(main())

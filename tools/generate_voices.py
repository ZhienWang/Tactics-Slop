"""Generates spoken voice clips for every line in data/dialogues.csv.

Each character's voice (a Microsoft neural voice, plus a speaking rate and
pitch tweak) is cast in data/voices.csv; the '*' row covers anyone not
listed. Clips land in assets/voices/<id>.ogg, where <id> comes from the
speaker and text (scripts.data_editor.voice_clip_id) - so re-running only
generates lines that are new or changed, and deletes clips for lines that
no longer exist. The game plays a line's clip if one is there and simply
stays silent if not.

Needs:  pip install edge-tts imageio-ffmpeg   (and internet while generating)
Run from the project root:   python tools/generate_voices.py
                             python tools/generate_voices.py --force   (redo all)
"""
import asyncio
import csv
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import edge_tts  # noqa: E402
import imageio_ffmpeg  # noqa: E402

from scripts.data_editor import VOICE_DIR, load_voice_cast_from_csv, voice_clip_id  # noqa: E402

OUT_DIR = os.path.join(ROOT, VOICE_DIR)


def dialogue_lines():
    with open(os.path.join(ROOT, "data", "dialogues.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yield row["character"].strip(), row["text"].strip()


def spoken_text(text):
    """What's actually said aloud: stage directions in parentheses, like
    "(Slips toward the Forum)", stay on screen but aren't read out."""
    return re.sub(r"\s*\([^)]*\)\s*", " ", text).strip()


async def synthesize(text, cast, mp3_path):
    speech = edge_tts.Communicate(spoken_text(text), cast["voice"], rate=cast["rate"], pitch=cast["pitch"])
    await speech.save(mp3_path)


def to_ogg(mp3_path, ogg_path):
    # Ogg Vorbis: plays in pygame on desktop and in the browser build.
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", mp3_path,
         "-c:a", "libvorbis", "-q:a", "4", ogg_path],
        check=True,
    )


async def main(force=False):
    os.makedirs(OUT_DIR, exist_ok=True)
    cast = load_voice_cast_from_csv()
    wanted = {}
    for speaker, text in dialogue_lines():
        wanted[voice_clip_id(speaker, text)] = (speaker, text)

    made = skipped = 0
    with tempfile.TemporaryDirectory() as tmp:
        for clip_id, (speaker, text) in wanted.items():
            ogg_path = os.path.join(OUT_DIR, f"{clip_id}.ogg")
            if os.path.exists(ogg_path) and not force:
                skipped += 1
                continue
            voice = cast.get(speaker) or cast["*"]
            mp3_path = os.path.join(tmp, f"{clip_id}.mp3")
            await synthesize(text, voice, mp3_path)
            to_ogg(mp3_path, ogg_path)
            made += 1
            print(f"  {speaker:10s} ({voice['voice']}): {text[:60]}")

    removed = 0
    for name in os.listdir(OUT_DIR):
        if name.endswith(".ogg") and name[:-4] not in wanted:
            os.remove(os.path.join(OUT_DIR, name))
            removed += 1
    print(f"\n{made} generated, {skipped} already up to date, {removed} stale clips removed -> {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main(force="--force" in sys.argv))

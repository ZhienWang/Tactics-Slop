"""Builds the browser version of the game with pygbag.

pygbag packs *everything* in the folder it's pointed at, so building from
the project root would ship the desktop builds (build_pyinstaller/, the
win64 zip), tests, SVG sources and backups - 80+ MB. Instead this stages
only what the game loads at runtime into build/road_to_jerusalem (pygbag
names the package after that folder), builds that, and
leaves the result in build/web (plus build/web.zip, ready to upload to
itch.io as an HTML5 game).

Run from the project root:   python tools/build_web.py
Then test locally with:       python tools/build_web.py --serve
                              (opens http://localhost:8000)
"""
import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE = os.path.join(ROOT, "build", "road_to_jerusalem")
OUTPUT = os.path.join(ROOT, "build", "web")

# Top-level files and folders the game needs at runtime.
INCLUDE = ["main.py", "scripts", "data", "assets"]

# Never shipped: tests, dev-only tools/art sources, and formats the game
# doesn't load (the web build plays .ogg, never .mp3/.wav).
EXCLUDE_DIRS = {"__pycache__", "units_original", "unit_svg", "individual_figures"}
EXCLUDE_FILES = {
    "lego_version_for_fun.jpg", "frame_example.jpg", "world_map_sample.png",
    "print_svg.py", "svg2png.py", "unit_art.py", "converted_art.py", "horse_art.py", "hero_art.py",
}
EXCLUDE_SUFFIXES = (".mp3", ".wav", ".pyc", ".svg")


def keep(name, is_dir):
    if is_dir:
        return name not in EXCLUDE_DIRS
    if name in EXCLUDE_FILES or name.endswith(EXCLUDE_SUFFIXES):
        return False
    return not (name.startswith("test_") and name.endswith(".py"))


def stage():
    if os.path.exists(STAGE):
        shutil.rmtree(STAGE)
    os.makedirs(STAGE)
    for entry in INCLUDE:
        source = os.path.join(ROOT, entry)
        target = os.path.join(STAGE, entry)
        if os.path.isfile(source):
            shutil.copy2(source, target)
            continue
        for folder, dirs, files in os.walk(source):
            dirs[:] = [d for d in dirs if keep(d, True)]
            out_folder = os.path.join(target, os.path.relpath(folder, source))
            os.makedirs(out_folder, exist_ok=True)
            for name in files:
                if keep(name, False):
                    shutil.copy2(os.path.join(folder, name), os.path.join(out_folder, name))


def build(serve=False):
    args = [sys.executable, "-m", "pygbag", "--title", "Road to Jerusalem"]
    if not serve:
        args.append("--build")
    args.append(STAGE)
    subprocess.run(args, check=True)


def publish():
    built = os.path.join(STAGE, "build", "web")
    # Replace build/web's contents rather than the folder itself, so a local
    # test server running from inside it doesn't block the rebuild on Windows.
    os.makedirs(OUTPUT, exist_ok=True)
    for name in os.listdir(OUTPUT):
        path = os.path.join(OUTPUT, name)
        shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    shutil.copytree(built, OUTPUT, dirs_exist_ok=True)
    archive = shutil.make_archive(os.path.join(ROOT, "build", "web"), "zip", OUTPUT)
    size = sum(os.path.getsize(p) for p in glob.glob(os.path.join(OUTPUT, "*.apk"))) / 1e6
    print(f"\nWeb build ready: {OUTPUT}  (game package {size:.1f} MB)")
    print(f"itch.io upload:  {archive}")


if __name__ == "__main__":
    serve = "--serve" in sys.argv
    stage()
    if serve:
        build(serve=True)
    else:
        build()
        publish()

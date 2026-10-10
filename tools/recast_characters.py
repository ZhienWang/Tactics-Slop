"""Recasts every character in the storyline with the character generator.

For each character in data/characters.csv and the stages' characters.csv,
rolls a random design (assets/figure_builder.py) suited to its role, writes
its token to assets/characters/<name>.png and points the CSVs'
portrait_path at it. The old art in assets/ is left alone, so this can be
undone by pointing portrait_path back.

  - Each design is seeded by the character's name: re-running gives the
    same cast, and the same name looks the same on every stage.
  - The named apostles keep their signature items (Peter's keys, John's
    chalice...) and their painted HUD portraits; Paul keeps his bald head
    and pointed beard.
  - Enemies are dressed for their role (shieldbearers, archers, medics,
    officers, temple guards). Every Legionnaire also gets a "converted"
    token - helmet off, a blue cloak - used once they join your side.
  - The protagonist gets one face in the four role colours.
  - Every design is recorded in data/character_designs.json, so the
    generator (tools/character_generator.py) can reopen and tweak it.

Run from the project root:   python tools/recast_characters.py
"""
import csv
import glob
import io
import json
import os
import random
import re
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "assets"))

import figure_builder as fb  # noqa: E402

OUT_DIR = os.path.join(ROOT, "assets", "characters")
DESIGNS_PATH = os.path.join(ROOT, "data", "character_designs.json")
CHARACTER_CSVS = [os.path.join(ROOT, "data", "roster.csv"), os.path.join(ROOT, "data", "characters.csv")] + sorted(glob.glob(os.path.join(ROOT, "data", "stages", "*", "characters.csv")))

# Token file names that the painted HUD portraits (assets/portraits) match.
PORTRAIT_NAMES = {"Peter": "simon_peter"}
FEMININE = {"Priscilla", "Lydia", "Mary", "Rhoda", "Tabitha", "Dorcas", "Lois", "Eunice", "Phoebe"}
SIGNATURE_ITEMS = {"Peter": "keys", "John": "chalice", "Mark": "staff", "Philip": "cross_staff", "Timothy": "knife",
                   "Luke": "purse", "Silas": "club", "Priscilla": "saw", "Aquila": "halberd", "Demas": "purse"}
# Recruits whose look comes from who they were before they joined.
LOOKS = {
    "Cornelius": {"body": "armor", "legs": "greaves", "helmet": "none", "hair": "short", "beard": "stubble",
                  "cape": "long", "cape_color": "crimson", "weapon": "sword", "arms": "hold"},
    "Jailer": {"body": "tunic", "legs": "sandals", "main": "brown", "trim": "slate", "weapon": "spear", "arms": "hold",
               "beard": "full"},
    "Lydia": {"main": "purple", "trim": "gold", "body": "robe"},
    "Lois": {"hair": "long", "hair_color": "grey", "helmet": "hood", "body": "robe"},
    "Apollos": {"body": "toga", "arms": "book", "weapon": "none"},
    "Eutychus": {"body": "tunic", "legs": "sandals", "beard": "none", "eyes": "closed", "weapon": "sling", "arms": "hold"},
}
# Not everyone in the company is a person.
DONKEYS = {"Barley": {"coat": "grey", "pack": "crimson"}}
ROLE_COLORS = {"analyst": "purple", "diplomat": "green", "sentinel": "blue", "explorer": "gold"}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def token_name(name):
    return PORTRAIT_NAMES.get(name, slug(name))


def design_for(name, team, char_class):
    """A role-appropriate random design, seeded by the name."""
    rng = random.Random(zlib.crc32(name.encode("utf-8")))
    enemy = team != "Player"
    soldier = enemy and (name.startswith("Legionnaire") or char_class in ("Officer", "Sergeant", "Soldier"))
    guard = name.startswith("Temple Guard")
    spec = fb.random_spec("enemy" if soldier else "person", rng)
    if name in FEMININE:
        spec.update(feminine=True, beard="none", hair=rng.choice(["long", "flowing"]))
    if name == "Paul":
        spec.update(hair="bald", beard="pointed", hair_color=rng.choice(["dark", "grey"]))
    if name in SIGNATURE_ITEMS:
        spec.update(weapon=SIGNATURE_ITEMS[name], arms="hold")
    elif not soldier:
        # Keys, chalices and the like belong to the apostles who carry them.
        spec["weapon"] = rng.choice(["none", "none", "staff"])
    if soldier:
        spec.update(body="armor", legs="greaves", arms="hold", helmet="legionary")
        if char_class == "Shieldbearer":
            spec.update(weapon="sword_shield")
        elif char_class == "Archer":
            spec.update(weapon="bow")
        elif char_class == "Medic":
            spec.update(weapon="purse", main="white")
        elif char_class == "Sergeant":
            spec.update(weapon="sword", cape="short", cape_color="crimson")
        elif char_class == "Officer":
            spec.update(helmet="centurion", weapon="spear", cape="long", cape_color="crimson", beard="stubble")
    if guard:
        spec.update(body=rng.choice(["tunic", "armor"]), helmet="headwrap", trim=rng.choice(["white", "gold"]),
                    weapon="spear", arms="hold", legs="sandals", cape="short", cape_color=rng.choice(["slate", "brown"]),
                    main=rng.choice(["slate", "brown", "teal"]))
    spec.update(LOOKS.get(name, {}))
    if spec["weapon"] != "none" and spec["arms"] == "book":
        spec["arms"] = "hold"
    return spec


def converted(spec):
    """A converted Legionnaire: helmet off, weapon down, a blue cloak."""
    return {**spec, "helmet": "none", "weapon": "none", "arms": "sides", "cape": "short", "cape_color": "blue",
            "main": "blue", "hair": spec["hair"] if spec["hair"] != "none" else "standard"}


def rewrite_csv(path, fix):
    raw = open(path, encoding="utf-8", newline="").read()
    reader = csv.DictReader(io.StringIO(raw))
    fields, rows = list(reader.fieldnames), list(reader)
    fix(rows)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\r\n" if "\r\n" in raw else "\n")
    writer.writeheader()
    writer.writerows(rows)
    open(path, "w", encoding="utf-8", newline="").write(out.getvalue())


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        designs = json.load(open(DESIGNS_PATH, encoding="utf-8"))
    except (OSError, ValueError):
        designs = {}
    cast = {}
    for path in CHARACTER_CSVS:
        for row in csv.DictReader(open(path, encoding="utf-8", newline="")):
            cast.setdefault(row["name"], (row["team"], row.get("class", "")))
    for name, (team, char_class) in sorted(cast.items()):
        key = token_name(name)
        if name in DONKEYS:
            fb.render_donkey_png(os.path.join(OUT_DIR, f"{key}.png"), **DONKEYS[name])
            print(f"  {name:28} -> assets/characters/{key}.png (donkey)")
            continue
        spec = design_for(name, team, char_class)
        fb.render_png(spec, os.path.join(OUT_DIR, f"{key}.png"))
        designs[key] = {"name": name, "team": "Person" if team == "Player" else "Enemy",
                        "portrait_path": f"assets/characters/{key}.png", "spec": spec}
        if name.startswith("Legionnaire") or char_class == "Officer":
            fb.render_png(converted(spec), os.path.join(OUT_DIR, f"{key}_converted.png"))
        print(f"  {name:28} -> assets/characters/{key}.png")
    # The protagonist: one face, in each role's colour.
    hero_rng = random.Random(zlib.crc32(b"hero"))
    hero = {**fb.random_spec("person", hero_rng), "arms": "book", "weapon": "none", "helmet": "none", "body": "robe"}
    for role, colour in ROLE_COLORS.items():
        fb.render_png({**hero, "main": colour}, os.path.join(OUT_DIR, f"hero_{role}.png"))
    print("  protagonist               -> assets/characters/hero_<role>.png")

    for path in CHARACTER_CSVS:
        def fix(rows):
            for row in rows:
                row["portrait_path"] = f"assets/characters/{token_name(row['name'])}.png"
        rewrite_csv(path, fix)
    with open(DESIGNS_PATH, "w", encoding="utf-8") as f:
        json.dump(designs, f, indent=2)
    print(f"Recast {len(cast)} characters; designs saved to data/character_designs.json")


if __name__ == "__main__":
    main()

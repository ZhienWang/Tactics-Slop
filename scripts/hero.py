"""The player's own character (the hero), built from the new-game survey.

The survey (data/survey.csv) asks thirty either/or questions, each leaning
toward one side of a personality pair - Extraversion/Introversion,
Sensing/iNtuition, Thinking/Feeling, Judging/Perceiving - and the four
majorities spell one of sixteen types. Each type is a class
(data/classes.csv) named for its 16Personalities archetype, with its own
signature skill (see resolve_signature in game_logic). Every pair has an odd
number of questions, so it never ties - the full survey asks 7/7/7/9, the
short version (the twelve questions marked `short`) 3 per pair, and the
super short one (the four marked `super_short`) a single question per pair. Should
a pair ever tie anyway (an edited survey), it goes to whichever way that
pair's first question was answered.

The result is kept as a small profile (name, type) so Continue can skip the
survey, and the hero joins the party in every battle, riding if the party
rides. Paul is the hero's advisor: his counsel for each class is shown on
the survey's result screen.
"""
import csv
import json
import os
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
PAIRS = ("EI", "SN", "TF", "JP")
DEFAULT_HERO_NAME = "Theophilus"
MAX_NAME_LENGTH = 14
ROLE_COLORS = {
    "Analyst": (136, 97, 154),
    "Diplomat": (51, 164, 116),
    "Sentinel": (66, 152, 180),
    "Explorer": (228, 174, 58),
}
# The hero's map token, by role (see assets/hero_art.py), and HUD face.
HERO_TOKEN = "assets/hero_{role}.png"
HERO_FACE = "assets/portraits/converts/convert_07.png"
PROFILE_PATH = os.path.join(os.path.expanduser("~"), ".road_to_jerusalem", "profile.json")


# Survey versions: the full thirty, or only the questions marked in the
# version's column of survey.csv.
SURVEY_VERSIONS = ("long", "short", "super_short")


def load_survey_from_csv(filepath=None, version="long"):
    """The survey's questions for `version` - "long" (all thirty), "short"
    (the twelve marked `short`) or "super_short" (the four marked
    `super_short`, one deciding each letter)."""
    filepath = filepath or os.path.join(DATA_DIR, "survey.csv")
    with open(filepath, newline="", encoding="utf-8") as f:
        return [
            {"id": int(row["id"]), "question": row["question"],
             "answers": [(row["answer_a"], row["letter_a"]), (row["answer_b"], row["letter_b"])]}
            for row in csv.DictReader(f)
            if version == "long" or (row.get(version) or "").strip() == "1"
        ]


def load_classes_from_csv(filepath=None):
    """{type code: class row}, with skills split and numbers parsed."""
    filepath = filepath or os.path.join(DATA_DIR, "classes.csv")
    numeric = ("speed", "mv", "jump", "mp", "magic_attack", "magic_defense", "faith", "bravery", "patience", "love")
    classes = {}
    with open(filepath, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row = dict(row)
            row["skills"] = row["skills"].split("|")
            for key in numeric:
                row[key] = int(row[key])
            classes[row["type"]] = row
    return classes


def score_survey(questions, answers):
    """The four-letter type from the chosen answer index (0 or 1) for each
    question. A tied pair goes to the letter chosen on its first question
    (and a pair with no answers at all to its first letter)."""
    counts, first = {}, {}
    for question, choice in zip(questions, answers):
        letter = question["answers"][choice][1]
        counts[letter] = counts.get(letter, 0) + 1
        pair = next(p for p in PAIRS if letter in p)
        first.setdefault(pair, letter)

    def pick(a, b):
        if counts.get(a, 0) != counts.get(b, 0):
            return a if counts.get(a, 0) > counts.get(b, 0) else b
        return first.get(a + b, a)
    return "".join(pick(a, b) for a, b in PAIRS)


def save_profile(profile, path=PROFILE_PATH):
    """Best effort - a browser build or a read-only home just won't remember."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile, f)
    except OSError:
        pass


def load_profile(path=PROFILE_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            profile = json.load(f)
    except (OSError, ValueError):
        return None
    return profile if profile.get("type") in load_classes_from_csv() and profile.get("name") else None


def free_tile_near(start, map_data, blocked):
    """The nearest walkable tile to `start` (breadth-first over the grid)
    that isn't in `blocked`, or None if the map is full."""
    rows, cols = len(map_data), len(map_data[0])
    seen, queue = {start}, deque([start])
    while queue:
        x, y = queue.popleft()
        if (x, y) not in blocked:
            return x, y
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < cols and 0 <= ny < rows and (nx, ny) not in seen:
                seen.add((nx, ny))
                queue.append((nx, ny))
    return None


def hero_character(profile, roster, map_data, prop_tiles, classes=None, leader_name="Paul"):
    """The hero's characters.csv-style entry for a battle: placed on the
    free tile nearest Paul (or the first Player unit), riding whatever Paul
    rides on this stage. None if there's no room."""
    classes = classes or load_classes_from_csv()
    row = classes[profile["type"]]
    players = [c for c in roster if c["team"] == "Player"]
    anchor = next((c for c in players if c["name"] == leader_name), players[0] if players else None)
    start = (anchor["x"], anchor["y"]) if anchor else (0, 0)
    blocked = {(c["x"], c["y"]) for c in roster} | set(prop_tiles)
    tile = free_tile_near(start, map_data, blocked)
    if tile is None:
        return None
    return {
        "name": profile["name"], "team": "Player", "class": row["class"],
        "x": tile[0], "y": tile[1],
        "speed": row["speed"], "mv": row["mv"], "jump": row["jump"], "mp": row["mp"],
        "skills": list(row["skills"]), "color": ROLE_COLORS[row["role"]],
        "portrait_path": HERO_TOKEN.format(role=row["role"].lower()),
        "face_portrait": HERO_FACE,
        "magic_attack": row["magic_attack"], "magic_defense": row["magic_defense"],
        "faith": row["faith"], "bravery": row["bravery"], "patience": row["patience"], "love": row["love"],
        "level": 1, "mount": anchor.get("mount", "") if anchor else "", "hero": True,
    }

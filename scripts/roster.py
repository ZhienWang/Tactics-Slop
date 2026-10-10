"""The company: everyone who can fight on your side, and when they join.

data/roster.csv holds each playable character once - stats, skills, token -
with a `joins` column naming the story scene after which they join you
("start" for those with you from the beginning) and a short `bio`. The
stages' characters.csv sheets hold only the enemy and any NPCs who fight
alongside you (Damascus's temple guards); the party comes from here.

Each stage's party_start.csv lists the tiles your party starts on, in
order - the leader takes the first - and how many there are is how many of
the company that stage has room for. Whoever is recruited and not benched
(on the world map's Unit screen) is deployed, in roster order, until the
tiles run out.
"""
import csv
import os

from scripts.data_editor import DATA_DIR, load_characters_from_csv
from scripts.hero import free_tile_near

ROSTER_PATH = os.path.join(DATA_DIR, "roster.csv")
PARTY_START_FILE = "party_start.csv"
START = "start"
LEADER = "Paul"


def load_roster(path=None):
    """[character dict, ...] in roster order, each also carrying `joins`
    and `bio`."""
    path = path or ROSTER_PATH
    characters = load_characters_from_csv(path)
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for character, row in zip(characters, rows):
        character["team"] = "Player"
        character["joins"] = (row.get("joins") or START).strip()
        character["bio"] = (row.get("bio") or "").strip()
    return characters


def starting_members(roster):
    return [c["name"] for c in roster if c["joins"] == START]


def recruits_for(scene_id, roster):
    """Who joins once `scene_id` has been played through."""
    return [c["name"] for c in roster if c["joins"] == scene_id]


def recruited_after(heard, roster):
    """Everyone who has joined by now, given the scenes already heard."""
    heard = set(heard)
    return [c["name"] for c in roster if c["joins"] == START or c["joins"] in heard]


def load_party_slots(stage_dir=None):
    """A stage's party start tiles [(x, y), ...]; [] if it has none."""
    path = os.path.join(stage_dir or DATA_DIR, PARTY_START_FILE)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [(int(row["x"]), int(row["y"])) for row in csv.DictReader(f)]


def save_party_slots(stage_dir, slots):
    with open(os.path.join(stage_dir, PARTY_START_FILE), "w", newline="", encoding="utf-8") as f:
        f.write("x,y\n" + "".join(f"{x},{y}\n" for x, y in slots))


def choose_party(roster, names, size):
    """The roster entries to deploy: those in `names` (everyone, if None),
    in roster order with the leader first, up to `size`."""
    pool = [c for c in roster if names is None or c["name"] in names]
    pool.sort(key=lambda c: c["name"] != LEADER)
    return pool[:size]


def deploy_party(members, slots, map_data, blocked, overrides=None):
    """Copies of `members` standing on `slots` in order. A slot that's taken
    (a prop, an enemy, a missing tile) falls back to the nearest free tile.
    `overrides` are applied to every member, e.g. {"mount": "horse"}."""
    blocked = set(blocked)
    placed = []
    for member, slot in zip(members, slots):
        tile = slot if slot not in blocked and 0 <= slot[1] < len(map_data) and 0 <= slot[0] < len(map_data[0]) \
            else free_tile_near(slot, map_data, blocked)
        if tile is None:
            break
        blocked.add(tile)
        placed.append({**member, **(overrides or {}), "x": tile[0], "y": tile[1]})
    return placed

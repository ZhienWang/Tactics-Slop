import csv
import io
import os
import random

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# --- 1. GENERATE DUMMY CSV DATA ---
# This simulates exporting spreadsheets from Excel/Google Sheets
MAP_CSV_DUMMY = """0,0,1,1,0,0
0,1,2,1,1,0
1,2,4,3,2,1
1,2,3,2,1,0
0,1,2,1,0,0
0,0,1,0,0,0"""

SKILLS_CSV_DUMMY = """skill_name,mp_cost,range,damage,type,r,g,b
Attack,0,1,30,Physical,200,50,50
Shoot,0,3,40,Physical,200,180,50
Fire,10,3,50,Magic,255,100,50
Blizzard,12,3,45,Magic,100,200,255
Chakra,0,1,-40,Heal,100,255,100
Fish net,0,3,0,Status,255,255,255"""

CHARACTERS_CSV_DUMMY = """name,team,class,x,y,speed,mv,jump,mp,skills,r,g,b,portrait_path
Ramza,Player,Knight,0,0,11,3,1,20,Attack|Chakra,50,120,240,
Agrias,Player,Mage,0,1,10,2,2,40,Attack|Fire|Blizzard,100,160,255,
Gafgarion,Enemy,Archer,5,4,12,3,1,10,Attack|Shoot,220,60,60,
Knight B,Enemy,Knight,4,5,9,2,1,0,Attack,180,50,50,"""

ITEMS_CSV_DUMMY = """item_name,effect,amount,target_scope,range,uses,r,g,b
Healing Salve,cure_status,0,ally,1,3,120,200,120
Ankh,revive,0.5,dead_ally,2,2,220,200,120
Myrrh,restore_mp,0,ally,1,2,170,110,210
Frankincense,buff_magic_attack,0.3,ally,1,2,200,150,70
Mustard Seed,faith_boost,20,ally,2,3,140,220,120"""

EQUIPMENT_CSV_DUMMY = """item_name,slot,stat_1,amount_1,stat_2,amount_2,description
Bronze Helm,helmet,magic_defense,8,,,A soldier's helm.
Leather Cuirass,armor,magic_defense,10,,,Boiled leather armor.
Bronze Greaves,pants,magic_defense,8,,,Fitted bronze leg plates.
Worn Sandals,sandals,mv,1,,,Well-traveled leather.
Bronze Shield,left_hand,magic_defense,10,,,A standard-issue shield.
Bronze Sword,right_hand,magic_attack,10,,,A short sword.
Simple Cord,necklace,faith,3,,,A plain cord.
Copper Ring,ring,bravery,3,,,A humble band of copper."""

GAME_SETTINGS_CSV_DUMMY = """setting_name,value
background_path,"""

DIALOGUES_CSV_DUMMY = """character,turn,text
Paul,1,"Welcome, friends. Our journey begins here."""

TERRAIN_TILE_PATHS = [
    "assets/grass.jpg",
    "assets/stone.png",
    "assets/moss.png",
    "assets/sand.png",
    "assets/snow.png",
    "assets/dirt.png",
    "assets/wood.png",
    "assets/cobblestone.png",
]

WATER_TILE_PATH = "assets/water.png"

# Relative frequency of each tile when randomly generating a terrain layout.
# Water is intentionally rarer, so it reads as a river/pond feature rather
# than a dominant terrain type.
TERRAIN_TILE_WEIGHTS = {
    "assets/grass.jpg": 3,
    "assets/stone.png": 2,
    "assets/moss.png": 2,
    "assets/sand.png": 2,
    "assets/snow.png": 2,
    "assets/dirt.png": 2,
    "assets/wood.png": 2,
    "assets/cobblestone.png": 2,
    WATER_TILE_PATH: 1,
}


def is_water_tile(terrain_path):
    """Whether a terrain image path represents a water/river tile."""
    return bool(terrain_path) and os.path.basename(terrain_path).lower() == "water.png"


# Each stage draws from a small, themed subset of tiles (3-4 max) rather
# than the full palette, so a map reads as one coherent place instead of a
# random patchwork.
TERRAIN_THEMES = {
    "coastal": {"assets/grass.jpg": 3, "assets/water.png": 2, "assets/sand.png": 2, "assets/dirt.png": 1},
    "village": {"assets/grass.jpg": 3, "assets/dirt.png": 2, "assets/wood.png": 2, "assets/stone.png": 1},
    "hillside": {"assets/stone.png": 3, "assets/cobblestone.png": 2, "assets/dirt.png": 2, "assets/grass.jpg": 1},
    "desert": {"assets/sand.png": 3, "assets/dirt.png": 2, "assets/stone.png": 2, "assets/water.png": 1},
    "mountain": {"assets/stone.png": 3, "assets/cobblestone.png": 2, "assets/snow.png": 2, "assets/dirt.png": 1},
    "city": {"assets/cobblestone.png": 3, "assets/stone.png": 2, "assets/wood.png": 2, "assets/sand.png": 1},
}

# Which theme each stage's terrain should draw from if its terrain_layout.csv
# is ever missing/malformed and generate_terrain_csv() has to fall back to
# generating one on the fly. Matches the theme each stage's actual saved
# terrain already uses, so a regenerated map still reads as the same place.
STAGE_THEMES = {
    "damascus": "desert",
    "jerusalem": "coastal",
    "antioch": "village",
    "philippi": "hillside",
    "corinth": "desert",
    "ephesus": "mountain",
    "rome": "city",
}


def generate_terrain_csv(rows=6, cols=6, seed=None, weights=None):
    """Create a varied terrain grid while avoiding same-tile clusters.

    `weights` optionally restricts generation to a themed subset of tiles
    (see TERRAIN_THEMES); it defaults to the full tile palette.
    """
    rng = random.Random(seed)
    tile_count = rows * cols
    weights = weights or TERRAIN_TILE_WEIGHTS
    total_weight = sum(weights.values())
    tiles = []
    for tile_path, weight in weights.items():
        tiles.extend([tile_path] * max(1, round(tile_count * weight / total_weight)))
    while len(tiles) < tile_count:
        tiles.append(next(iter(weights)))
    while len(tiles) > tile_count:
        tiles.pop()
    rng.shuffle(tiles)
    grid = []

    for y in range(rows):
        grid.append([])
        for x in range(cols):
            choices = []
            for index, tile in enumerate(tiles):
                same_neighbors = 0
                if x > 0 and grid[y][x - 1] == tile:
                    same_neighbors += 1
                if y > 0 and grid[y - 1][x] == tile:
                    same_neighbors += 1
                choices.append((same_neighbors, index, tile))
            lowest_neighbor_count = min(choice[0] for choice in choices)
            best_choices = [choice for choice in choices if choice[0] == lowest_neighbor_count]
            _, selected_index, selected_tile = rng.choice(best_choices)
            grid[y].append(selected_tile)
            tiles.pop(selected_index)

    return "\n".join(",".join(row) for row in grid)


def generate_map_csv(rows=6, cols=6, seed=None, max_height=2):
    """Create a smooth elevation grid radiating from a random peak, rather
    than per-tile noise, so it reads as one hill/ridge instead of jagged
    static. Used as a fallback when a stage has no hand-authored
    map_layout.csv (load_map_from_csv() would otherwise just crash)."""
    rng = random.Random(seed)
    peak_x, peak_y = rng.randrange(cols), rng.randrange(rows)
    max_dist = max(1, (rows + cols) // 2)
    grid = []
    for y in range(rows):
        row = []
        for x in range(cols):
            dist = abs(x - peak_x) + abs(y - peak_y)
            base = max(0, max_height - round(max_height * dist / max_dist))
            jitter = rng.choice([-1, 0, 0, 0, 1])
            row.append(max(0, min(max_height, base + jitter)))
        grid.append(row)
    return "\n".join(",".join(str(v) for v in row) for row in grid)


def generate_dummy_csv_files():
    """Writes the dummy text configurations to actual CSV files on disk."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "map_layout.csv"), "w", newline="") as f:
        f.write(MAP_CSV_DUMMY.strip())
        
    with open(os.path.join(DATA_DIR, "skills.csv"), "w", newline="") as f:
        f.write(SKILLS_CSV_DUMMY.strip())
        
    with open(os.path.join(DATA_DIR, "characters.csv"), "w", newline="") as f:
        f.write(CHARACTERS_CSV_DUMMY.strip())

    save_terrain_layout_csv(os.path.join(DATA_DIR, "terrain_layout.csv"), load_terrain_from_text(generate_terrain_csv()))

    with open(os.path.join(DATA_DIR, "game_settings.csv"), "w", newline="") as f:
        f.write(GAME_SETTINGS_CSV_DUMMY.strip())

    with open(os.path.join(DATA_DIR, "dialogues.csv"), "w", newline="", encoding="utf-8") as f:
        f.write(DIALOGUES_CSV_DUMMY.strip())

    with open(os.path.join(DATA_DIR, "items.csv"), "w", newline="") as f:
        f.write(ITEMS_CSV_DUMMY.strip())

    with open(os.path.join(DATA_DIR, "equipment.csv"), "w", newline="") as f:
        f.write(EQUIPMENT_CSV_DUMMY.strip())

    print("Successfully generated dummy files: map_layout.csv, skills.csv, characters.csv, terrain_layout.csv, game_settings.csv, dialogues.csv, items.csv, equipment.csv")


# --- 2. THE CSV PARSING PIPELINE ---

def normalize_height(value):
    """A tile height snapped to the nearest half step. Whole heights come
    back as ints, so existing all-integer maps load and save exactly as
    before; a .5 height stays a float and is drawn as a slope tile ramping
    between its lower and higher neighbors (see controls.slope_uphill_direction)."""
    height = round(float(value) * 2) / 2
    return int(height) if height.is_integer() else height


def load_map_from_csv(filepath=None):
    """Reads a grid of tile heights - whole numbers, or half steps (0.5,
    1.5, ...) for slopes."""
    map_grid = []
    filepath = filepath or os.path.join(DATA_DIR, "map_layout.csv")
    with open(filepath, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            if row: # Skip empty lines
                map_grid.append([normalize_height(tile) for tile in row])
    return map_grid


def load_skills_from_csv(filepath=None):
    """Parses skill rows into a configured nested dictionary."""
    skills_registry = {}
    filepath = filepath or os.path.join(DATA_DIR, "skills.csv")
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skills_registry[row["skill_name"]] = {
                "mp_cost": int(row["mp_cost"]),
                "range": int(row["range"]),
                "damage": int(row["damage"]),
                "type": row["type"],
                "color": (int(row["r"]), int(row["g"]), int(row["b"]))
            }
    return skills_registry


def load_items_from_csv(filepath=None):
    """Parses consumable item rows into a configured nested dictionary."""
    items_registry = {}
    filepath = filepath or os.path.join(DATA_DIR, "items.csv")
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items_registry[row["item_name"]] = {
                "effect": row["effect"],
                "amount": float(row["amount"]),
                "target_scope": row["target_scope"],
                "range": int(row["range"]),
                "uses": int(row["uses"]),
                "color": (int(row["r"]), int(row["g"]), int(row["b"])),
            }
    return items_registry


# The two ring slots share this same pool; every other slot has its own.
EQUIPMENT_SLOTS = ["helmet", "armor", "pants", "sandals", "left_hand", "right_hand", "necklace", "ring"]
UNIT_EQUIPMENT_SLOTS = ["helmet", "armor", "pants", "sandals", "left_hand", "right_hand", "necklace", "ring_1", "ring_2"]


def load_equipment_from_csv(filepath=None):
    """Parses the pregenerated equipment catalog into a dict keyed by item
    name, each with its slot, stat bonuses, and flavor text."""
    equipment_registry = {}
    filepath = filepath or os.path.join(DATA_DIR, "equipment.csv")
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats = {}
            if row.get("stat_1"):
                stats[row["stat_1"]] = int(row["amount_1"])
            if row.get("stat_2"):
                stats[row["stat_2"]] = int(row["amount_2"])
            equipment_registry[row["item_name"]] = {
                "slot": row["slot"],
                "stats": stats,
                "description": row.get("description", ""),
            }
    return equipment_registry


def equipment_by_slot(equipment_registry):
    """Groups the equipment catalog by slot, e.g. grouped["ring"] lists every
    item either ring slot can equip."""
    grouped = {slot: [] for slot in EQUIPMENT_SLOTS}
    for name, data in equipment_registry.items():
        grouped.setdefault(data["slot"], []).append(name)
    return grouped


# Daily Devotion Books: a PoE2-gem-socket-style system where each disciple
# carries up to 5 books into battle. Unlike equipment slots, every book slot
# is generic - any book from the catalog can go in any of the 5 slots.
BOOK_SLOTS = ["book_1", "book_2", "book_3", "book_4", "book_5"]

# How many of a unit's own battle turns a book must be held for before its
# reading level advances - checked highest-threshold-first.
READING_LEVEL_THRESHOLDS = [
    (30, "Mastered"),
    (20, "Devoted"),
    (10, "Learned"),
    (0, "Novice"),
]


def reading_level(turns_held):
    """The disciple's familiarity with a held book, based on how many of
    their own battle turns they've carried it - mirrors a PoE2 gem's
    level-up-by-use progression."""
    for threshold, label in READING_LEVEL_THRESHOLDS:
        if turns_held >= threshold:
            return label
    return "Novice"


def load_books_from_csv(filepath=None):
    """Parses the Daily Devotion Book catalog into a dict keyed by book
    name, each naming the stat it nurtures in whoever carries it."""
    books_registry = {}
    filepath = filepath or os.path.join(DATA_DIR, "books.csv")
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            books_registry[row["book_name"]] = {
                "stat": row["stat"],
                "description": row.get("description", ""),
            }
    return books_registry


def load_terrain_types(filepath=None):
    """Parses the terrain lookup (code, name, asset) that terrain_layout.csv
    files are written in terms of - each cell is a single-letter code, so
    the layouts stay readable as a grid. Returns {code: asset path}."""
    filepath = filepath or os.path.join(DATA_DIR, "terrain_types.csv")
    with open(filepath, "r", newline="") as f:
        return {row["code"].strip(): row["asset"].strip() for row in csv.DictReader(f)}


def load_terrain_from_csv(filepath=None, terrain_types=None):
    """Parses a grid of terrain codes, resolved to their tile image paths
    through terrain_types.csv. An unknown code fails loudly, naming the
    cell, rather than silently drawing a missing texture."""
    terrain_types = terrain_types or load_terrain_types()
    terrain_grid = []
    filepath = filepath or os.path.join(DATA_DIR, "terrain_layout.csv")
    with open(filepath, "r") as f:
        reader = csv.reader(f)
        for y, row in enumerate(reader):
            if not row:
                continue
            grid_row = []
            for x, cell in enumerate(row):
                code = cell.strip()
                if code not in terrain_types:
                    raise ValueError(f"{filepath}: unknown terrain code {code!r} at x={x}, y={y}")
                grid_row.append(terrain_types[code])
            terrain_grid.append(grid_row)
    return terrain_grid


def load_terrain_from_text(terrain_text):
    """Parses a generated terrain CSV string into a terrain grid."""
    return [
        [cell.strip() for cell in row]
        for row in csv.reader(io.StringIO(terrain_text))
        if row
    ]


def load_map_layers_csv(filepath=None):
    """Parses the sparse "one row per physical tile" map format the map
    editor works in: {x, y, z, terrain}. Unlike map_layout.csv/
    terrain_layout.csv (one height + one texture per cell, always), a
    column (x, y) can hold zero tiles (a hole) or several (a bridge/
    platform floating above a gap). Missing file just means "no
    editor-authored layers yet" - returns an empty list rather than
    raising, matching load_stage_manifest's tolerance."""
    filepath = filepath or os.path.join(DATA_DIR, "map_layers.csv")
    if not os.path.exists(filepath):
        return []
    tiles = []
    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tiles.append({
                "x": int(row["x"]),
                "y": int(row["y"]),
                "z": normalize_height(row["z"]),
                "terrain": row["terrain"].strip(),
            })
    return tiles


def load_props_from_csv(filepath=None):
    """Parses a stage's scenery props - trees so far - as {x, y, prop,
    height}, where height is how many map height units tall the prop
    stands. A prop owns its whole tile: nothing can walk onto it. Most
    stages have no props, so a missing file just means "no scenery here"
    and returns an empty list rather than raising, matching
    load_map_layers_csv's tolerance."""
    filepath = filepath or os.path.join(DATA_DIR, "props.csv")
    if not os.path.exists(filepath):
        return []
    props = []
    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            props.append({
                "x": int(row["x"]),
                "y": int(row["y"]),
                "prop": row["prop"].strip(),
                "height": normalize_height(row["height"]),
            })
    return props


def load_effects_from_csv(filepath=None):
    """The particle-effect library (data/effects.csv) as {name: row dict};
    scripts.effects.EffectSpec turns each row into a playable effect."""
    filepath = filepath or os.path.join(DATA_DIR, "effects.csv")
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r", newline="", encoding="utf-8") as f:
        return {row["name"].strip(): row for row in csv.DictReader(f) if row.get("name", "").strip()}


# When a bound effect plays: on every use, or only on a given outcome.
EFFECT_OUTCOMES = ("always", "hit", "miss", "blocked", "convert", "shaken", "despair")
# Which unit(s) it plays on: the skill's target, its user, or - for area
# skills like Lead - every unit it affected.
EFFECT_ANCHORS = ("target", "caster", "recipients")


def load_skill_effects_from_csv(filepath=None):
    """data/skill_effects.csv - which effects play when a skill or item is
    used - as {skill_or_item: [{"effect", "anchor", "on"}, ...]}. A skill
    can have several rows (effects layered, or different ones per outcome).
    Names starting with '@' are game events rather than skills: @morale,
    @rekindle, @lead_fade, @despair_turn, @stunned, @snared, @level_up."""
    filepath = filepath or os.path.join(DATA_DIR, "skill_effects.csv")
    bindings = {}
    if not os.path.exists(filepath):
        return bindings
    with open(filepath, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            skill = row.get("skill", "").strip()
            effect = row.get("effect", "").strip()
            if not skill or not effect:
                continue
            anchor = (row.get("anchor") or "target").strip() or "target"
            on = (row.get("on") or "always").strip() or "always"
            bindings.setdefault(skill, []).append({"effect": effect, "anchor": anchor, "on": on})
    return bindings


# Spoken dialogue: one clip per line, generated by tools/generate_voices.py
# from the cast in data/voices.csv.
VOICE_DIR = os.path.join("assets", "voices")


def voice_clip_id(speaker, text):
    """A dialogue line's voice clip name, from who says it and what they
    say - so editing a line's text gives it a fresh clip, and reordering
    lines in dialogues.csv never mismatches voices."""
    import hashlib
    return hashlib.sha1(f"{speaker.strip()}|{text.strip()}".encode("utf-8")).hexdigest()[:16]


def load_voice_cast_from_csv(filepath=None):
    """data/voices.csv as {character: {"voice", "rate", "pitch"}}; the '*'
    row is the voice for anyone not listed."""
    filepath = filepath or os.path.join(DATA_DIR, "voices.csv")
    cast = {}
    with open(filepath, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cast[row["character"].strip()] = {
                "voice": row["voice"].strip(),
                "rate": (row.get("rate") or "+0%").strip(),
                "pitch": (row.get("pitch") or "+0Hz").strip(),
            }
    return cast


WEATHER_TYPES = ("sunny", "rain", "heavy_rain", "storm")


def load_weather_from_csv(filepath):
    """A stage's weather (one of WEATHER_TYPES), from its weather.csv - a
    setting_name,value file like game_settings.csv with a `weather` row.
    Like props.csv it's optional: no file, or an unrecognized value, means
    "sunny" rather than an error."""
    if not filepath or not os.path.exists(filepath):
        return "sunny"
    with open(filepath, "r", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("setting_name", "").strip() == "weather":
                value = row.get("value", "").strip().lower()
                return value if value in WEATHER_TYPES else "sunny"
    return "sunny"


def save_map_layers_csv(filepath, tiles):
    """Writes the sparse tile list back out, sorted by (y, x, z) so repeat
    saves of an unchanged map produce a stable diff."""
    ordered = sorted(tiles, key=lambda t: (t["y"], t["x"], t["z"]))
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["x", "y", "z", "terrain"])
        for tile in ordered:
            writer.writerow([tile["x"], tile["y"], tile["z"], tile["terrain"]])


def dense_grids_to_tiles(map_grid, terrain_grid):
    """Converts an existing stage's loaded MAP_DATA + TERRAIN_LAYOUT (one
    height/texture per cell, always) into the sparse tile-list format - one
    tile per cell, a straight 1:1 conversion. This is how the editor loads
    an existing single-layer stage to continue editing it."""
    tiles = []
    for y, row in enumerate(map_grid):
        for x, height in enumerate(row):
            terrain = terrain_grid[y][x] if y < len(terrain_grid) and x < len(terrain_grid[y]) else ""
            tiles.append({"x": x, "y": y, "z": height, "terrain": terrain})
    return tiles


def tiles_to_dense_grids(tiles, rows, cols):
    """Converts sparse tiles back to the legacy dense grids the live game
    engine reads, but only if every (x, y) in the rows x cols rectangle has
    exactly one tile - no holes, no bridges. Returns None otherwise (the
    caller should fall back to saving map_layers.csv only)."""
    by_column = {}
    for tile in tiles:
        by_column.setdefault((tile["x"], tile["y"]), []).append(tile)

    map_grid = [[0] * cols for _ in range(rows)]
    terrain_grid = [[""] * cols for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            column = by_column.get((x, y), [])
            if len(column) != 1:
                return None
            map_grid[y][x] = column[0]["z"]
            terrain_grid[y][x] = column[0]["terrain"]
    return map_grid, terrain_grid


def save_map_layout_csv(filepath, map_grid):
    """Writes a dense height grid in the same format load_map_from_csv
    reads - previously only ever read (maps were hand-authored or
    generated in-memory), never written by the game itself."""
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        for row in map_grid:
            writer.writerow(row)


def save_terrain_layout_csv(filepath, terrain_grid, terrain_types=None):
    """Writes a dense terrain-texture grid in the same format
    load_terrain_from_csv reads - each tile path as its terrain code."""
    codes = {asset: code for code, asset in (terrain_types or load_terrain_types()).items()}
    missing = {path for row in terrain_grid for path in row if path not in codes}
    if missing:
        raise ValueError(f"no terrain code in terrain_types.csv for {sorted(missing)}")
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        for row in terrain_grid:
            writer.writerow([codes[path] for path in row])


def load_settings_from_csv(filepath=None):
    """Parses simple key/value game settings from CSV."""
    settings = {}
    filepath = filepath or os.path.join(DATA_DIR, "game_settings.csv")
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            settings[row["setting_name"]] = row["value"]
    return settings


def load_dialogues_from_csv(filepath=None, map_id=None):
    """Parses dialogue lines grouped by turn, optionally filtered to a single map/stage."""
    dialogues = {}
    filepath = filepath or os.path.join(DATA_DIR, "dialogues.csv")
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if map_id is not None and row.get("map", "").strip() != map_id:
                continue
            # A turn number, or a named scripted scene (e.g. "light" - see
            # STAGE_SCENES in game_logic).
            turn = row["turn"].strip()
            turn = int(turn) if turn.isdigit() else turn
            line = (row["character"].strip(), row["text"].strip())
            dialogues.setdefault(turn, []).append(line)
    return dialogues


def load_stage_manifest(filepath=None):
    """Parses the stage manifest, resolving each stage's data file paths."""
    stages = {}
    filepath = filepath or os.path.join(DATA_DIR, "stages.csv")
    if not os.path.exists(filepath):
        return stages
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stages[row["node_id"]] = {
                "node_id": row["node_id"],
                "title": row["title"],
                "map_layout": os.path.join(DATA_DIR, row["map_layout"]),
                "terrain_layout": os.path.join(DATA_DIR, row["terrain_layout"]),
                "characters": os.path.join(DATA_DIR, row["characters"]),
            }
    return stages


def load_world_map_nodes(filepath=None):
    """Parses the world map's node layout (screen position, type, and which
    other nodes it connects to). Returns (nodes, start_node_id)."""
    filepath = filepath or os.path.join(DATA_DIR, "world_map_nodes.csv")
    nodes = {}
    start_node_id = None
    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            node_id = row["node_id"].strip()
            connections = [c.strip() for c in row["connections"].split("|") if c.strip()]
            nodes[node_id] = {
                "pos": (int(row["x"]), int(row["y"])),
                "name": row["name"].strip(),
                "type": row["type"].strip(),
                "connections": connections,
            }
            if row.get("start", "").strip() == "1":
                start_node_id = node_id
    if start_node_id is None and nodes:
        start_node_id = next(iter(nodes))
    return nodes, start_node_id


def load_escape_tiles_from_csv(filepath):
    """A stage's exit tiles (escape.csv: x,y) - where fleeing units leave the
    battle. A stage without the file has none."""
    if not filepath or not os.path.exists(filepath):
        return set()
    with open(filepath, "r", newline="") as f:
        return {(int(row["x"]), int(row["y"])) for row in csv.DictReader(f)}


def load_characters_from_csv(filepath=None):
    """Parses character stats and handles delimited skill lists."""
    character_list = []
    filepath = filepath or os.path.join(DATA_DIR, "characters.csv")
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Reconstruct the character map dictionary expected by the Unit class
            char_data = {
                "name": row["name"],
                "team": row["team"],
                "class": row.get("class", "").strip(),
                "x": int(row["x"]),
                "y": int(row["y"]),
                "speed": int(row["speed"]),
                "mv": int(row["mv"]),
                "jump": int(row["jump"]),
                "mp": int(row["mp"]),
                # Split the pipe-delimited string back into a real Python list
                "skills": row["skills"].split("|") if row["skills"] else [],
                "color": (int(row["r"]), int(row["g"]), int(row["b"])),
                "portrait_path": row.get("portrait_path", "").strip(),
                # Optional: everyone starts at Lv 1 unless a level is given.
                "level": int(row.get("level") or 1),
                # Optional: what the unit rides, e.g. "horse" (see MOUNTS).
                "mount": (row.get("mount") or "").strip(),
                # Optional: a HUD face portrait, overriding the one matched
                # from portrait_path (for units borrowing another's token).
                "face_portrait": (row.get("face_portrait") or "").strip(),
            }
            for attribute in [
                "magic_attack", "magic_defense",
                "faith", "bravery", "patience", "love",
            ]:
                char_data[attribute] = int(row[attribute])
            character_list.append(char_data)
    return character_list


def update_character_positions_csv(filepath, positions):
    """Rewrites only the x/y columns of a characters.csv for names present
    in `positions` ({name: (x, y)}), leaving every other column (skills,
    stats, portrait_path, ...) and the column order untouched. Reads/writes
    raw string rows rather than round-tripping through
    load_characters_from_csv's typed representation, so nothing gets
    reformatted along the way."""
    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    for row in rows:
        if row["name"] in positions:
            x, y = positions[row["name"]]
            row["x"] = str(x)
            row["y"] = str(y)

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# --- TEST EXECUTOR ---
if __name__ == "__main__":
    # Create the files
    generate_dummy_csv_files()
    
    print("\n--- Testing Parser Verification ---")
    # Parse the files back
    loaded_map = load_map_from_csv()
    loaded_skills = load_skills_from_csv()
    loaded_chars = load_characters_from_csv()
    
    print(f"Loaded Map Dimensions: {len(loaded_map)}x{len(loaded_map[0])}")
    print(f"Loaded Skills: {list(loaded_skills.keys())}")
    print(f"Loaded Total Roster Size: {len(loaded_chars)} units")
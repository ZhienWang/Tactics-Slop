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

GAME_SETTINGS_CSV_DUMMY = """setting_name,value
background_path,"""

DIALOGUES_CSV_DUMMY = """character,turn,text
Jesus,1,"Welcome, friends. Our journey begins here."""

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
    "galilee": "coastal",
    "cana": "village",
    "nazareth": "hillside",
    "samaria": "desert",
    "bethany": "mountain",
    "jerusalem": "city",
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

    with open(os.path.join(DATA_DIR, "terrain_layout.csv"), "w", newline="") as f:
        f.write(generate_terrain_csv())

    with open(os.path.join(DATA_DIR, "game_settings.csv"), "w", newline="") as f:
        f.write(GAME_SETTINGS_CSV_DUMMY.strip())

    with open(os.path.join(DATA_DIR, "dialogues.csv"), "w", newline="", encoding="utf-8") as f:
        f.write(DIALOGUES_CSV_DUMMY.strip())

    print("Successfully generated dummy files: map_layout.csv, skills.csv, characters.csv, terrain_layout.csv, game_settings.csv, dialogues.csv")


# --- 2. THE CSV PARSING PIPELINE ---

def load_map_from_csv(filepath=None):
    """Reads a grid of integers representing height tiles."""
    map_grid = []
    filepath = filepath or os.path.join(DATA_DIR, "map_layout.csv")
    with open(filepath, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            if row: # Skip empty lines
                map_grid.append([int(tile) for tile in row])
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


def load_terrain_from_csv(filepath=None):
    """Parses terrain tile image paths from a CSV grid."""
    terrain_grid = []
    filepath = filepath or os.path.join(DATA_DIR, "terrain_layout.csv")
    with open(filepath, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            if row:
                terrain_grid.append([cell.strip() for cell in row])
    return terrain_grid


def load_terrain_from_text(terrain_text):
    """Parses a generated terrain CSV string into a terrain grid."""
    return [
        [cell.strip() for cell in row]
        for row in csv.reader(io.StringIO(terrain_text))
        if row
    ]


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
            turn = int(row["turn"])
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
                "portrait_path": row.get("portrait_path", "").strip()
            }
            for attribute in [
                "magic_attack", "magic_defense",
                "faith", "bravery", "patience", "love",
            ]:
                char_data[attribute] = int(row[attribute])
            character_list.append(char_data)
    return character_list


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
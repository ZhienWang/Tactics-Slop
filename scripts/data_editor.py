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

CHARACTERS_CSV_DUMMY = """name,team,class,x,y,speed,mv,jump,hp,mp,skills,r,g,b,portrait_path
Ramza,Player,Knight,0,0,11,3,1,120,20,Attack|Chakra,50,120,240,
Agrias,Player,Mage,0,1,10,2,2,100,40,Attack|Fire|Blizzard,100,160,255,
Gafgarion,Enemy,Archer,5,4,12,3,1,140,10,Attack|Shoot,220,60,60,
Knight B,Enemy,Knight,4,5,9,2,1,110,0,Attack,180,50,50,"""

GAME_SETTINGS_CSV_DUMMY = """setting_name,value
background_path,"""

DIALOGUES_CSV_DUMMY = """character,turn,text
Jesus,1,"Welcome, friends. Our journey begins here."""

TERRAIN_TILE_PATHS = [
    "assets/grass.jpg",
    "assets/stone.png",
    "assets/moss.png",
]


def generate_terrain_csv(rows=6, cols=6, seed=None):
    """Create a varied terrain grid while avoiding same-tile clusters."""
    rng = random.Random(seed)
    tile_count = rows * cols
    tiles = (
        [TERRAIN_TILE_PATHS[0]] * (tile_count // 2)
        + [TERRAIN_TILE_PATHS[1]] * (tile_count // 4)
        + [TERRAIN_TILE_PATHS[2]] * (tile_count - (tile_count // 2) - (tile_count // 4))
    )
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


def load_dialogues_from_csv(filepath=None):
    """Parses dialogue lines grouped by turn in CSV order."""
    dialogues = {}
    filepath = filepath or os.path.join(DATA_DIR, "dialogues.csv")
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
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
                "title": row["title"],
                "map_layout": os.path.join(DATA_DIR, row["map_layout"]),
                "terrain_layout": os.path.join(DATA_DIR, row["terrain_layout"]),
                "characters": os.path.join(DATA_DIR, row["characters"]),
                "dialogues": os.path.join(DATA_DIR, row["dialogues"]) if row.get("dialogues") else None,
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
                "hp": int(row["hp"]),
                "mp": int(row["mp"]),
                # Split the pipe-delimited string back into a real Python list
                "skills": row["skills"].split("|") if row["skills"] else [],
                "color": (int(row["r"]), int(row["g"]), int(row["b"])),
                "portrait_path": row.get("portrait_path", "").strip()
            }
            for attribute in [
                "physical_attack", "physical_defense", "magic_attack", "magic_defense",
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
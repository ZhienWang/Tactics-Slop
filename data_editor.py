import csv
import io

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
Fire,10,3,50,Magic,255,100,50
Blizzard,12,3,45,Magic,100,200,255
Chakra,0,1,-40,Heal,100,255,100"""

CHARACTERS_CSV_DUMMY = """name,team,x,y,speed,mv,jump,hp,mp,skills,r,g,b
Ramza,Player,0,0,11,3,1,120,20,Attack|Chakra,50,120,240
Agrias,Player,0,1,10,2,2,100,40,Attack|Fire|Blizzard,100,160,255
Gafgarion,Enemy,5,4,12,3,1,140,10,Attack,220,60,60
Knight B,Enemy,4,5,9,2,1,110,0,Attack,180,50,50"""


def generate_dummy_csv_files():
    """Writes the dummy text configurations to actual CSV files on disk."""
    with open("map_layout.csv", "w", newline="") as f:
        f.write(MAP_CSV_DUMMY.strip())
        
    with open("skills.csv", "w", newline="") as f:
        f.write(SKILLS_CSV_DUMMY.strip())
        
    with open("characters.csv", "w", newline="") as f:
        f.write(CHARACTERS_CSV_DUMMY.strip())
    print("Successfully generated dummy files: map_layout.csv, skills.csv, characters.csv")


# --- 2. THE CSV PARSING PIPELINE ---

def load_map_from_csv(filepath="map_layout.csv"):
    """Reads a grid of integers representing height tiles."""
    map_grid = []
    with open(filepath, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            if row: # Skip empty lines
                map_grid.append([int(tile) for tile in row])
    return map_grid


def load_skills_from_csv(filepath="skills.csv"):
    """Parses skill rows into a configured nested dictionary."""
    skills_registry = {}
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


def load_characters_from_csv(filepath="characters.csv"):
    """Parses character stats and handles delimited skill lists."""
    character_list = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Reconstruct the character map dictionary expected by the Unit class
            char_data = {
                "name": row["name"],
                "team": row["team"],
                "x": int(row["x"]),
                "y": int(row["y"]),
                "speed": int(row["speed"]),
                "mv": int(row["mv"]),
                "jump": int(row["jump"]),
                "hp": int(row["hp"]),
                "mp": int(row["mp"]),
                # Split the pipe-delimited string back into a real Python list
                "skills": row["skills"].split("|") if row["skills"] else [],
                "color": (int(row["r"]), int(row["g"]), int(row["b"]))
            }
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
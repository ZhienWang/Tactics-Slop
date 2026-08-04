# -- vibe coding experiments --
import os
import pygame
import sys
import heapq
from data_editor import generate_dummy_csv_files, load_map_from_csv, load_skills_from_csv, load_characters_from_csv

# --- CONFIGURATION ---
SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 700
TILE_WIDTH = 64
TILE_HEIGHT = 32

BG_COLOR = (25, 25, 35)
GRID_COLOR = (80, 80, 90)
CURSOR_COLOR = (255, 215, 0)
CHARACTER_PORTRAITS = {}

# ==========================================
# --- EDITABLE DATA MODELS (THE EDITORS) ---
# ==========================================

MAP_DATA = []
MAP_ROWS = 0
MAP_COLS = 0
SKILL_REGISTRY = {}
CHARACTER_ROSTER = []

# The data will be loaded from CSV files by the main entry point.
# If those files do not exist, generate sample CSVs first.
# ==========================================

# --- ENGINE UNIT ENGINE OBJECT ---
class Unit:
    def __init__(self, data):
        self.name = data["name"]
        self.team = data["team"]
        self.x = data["x"]
        self.y = data["y"]
        self.speed = data["speed"]
        self.mv = data["mv"]
        self.jump = data["jump"]
        self.max_hp = data["hp"]
        self.hp = data["hp"]
        self.max_mp = data["mp"]
        self.mp = data["mp"]
        self.skills = data["skills"]
        self.color = data["color"]
        
        self.ct = 0
        self.tp = 0
        self.has_moved = False
        self.has_acted = False

    def is_alive(self):
        return self.hp > 0

# --- A* PATHFINDING ALGORITHM ---
def get_valid_moves_a_star(unit, units_list):
    """
    Calculates valid movement tiles using a true A* search approach.
    Accounts for solid obstacles (other living units) and height limits (jump stat).
    """
    start_pos = (unit.x, unit.y)
    # Priority Queue elements: (cost, x, y)
    open_set = [(0, unit.x, unit.y)]
    # Tracks the shortest path distance found to any tile
    g_score = {start_pos: 0}
    
    # Track coordinates of all other living combatants to treat them as solid walls
    occupied_tiles = {(u.x, u.y) for u in units_list if u.is_alive() and u != unit}
    
    valid_tiles = []

    while open_set:
        cost, cx, cy = heapq.heappop(open_set)

        if cost > unit.mv:
            continue
            
        if (cx, cy) not in valid_tiles:
            valid_tiles.append((cx, cy))

        # Check 4-Cardinal Directions (Up, Down, Left, Right)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = cx + dx, cy + dy
            
            # Ensure index stays within map grid constraints
            if 0 <= nx < MAP_COLS and 0 <= ny < MAP_ROWS:
                if (nx, ny) in occupied_tiles:
                    continue  # Blocked by another unit
                
                # Check height jump limits between tiles
                current_z = MAP_DATA[cy][cx]
                target_z = MAP_DATA[ny][nx]
                
                if abs(current_z - target_z) <= unit.jump:
                    tentative_g = g_score[(cx, cy)] + 1
                    
                    if tentative_g <= unit.mv and (tentative_g < g_score.get((nx, ny), float('inf'))):
                        g_score[(nx, ny)] = tentative_g
                        heapq.heappush(open_set, (tentative_g, nx, ny))
                        
    return valid_tiles

# --- SKILL RANGE TARGET FILTER ---
def get_skill_targets(unit, skill_name):
    targets = []
    skill_data = SKILL_REGISTRY[skill_name]
    max_range = skill_data["range"]
    
    for x in range(MAP_COLS):
        for y in range(MAP_ROWS):
            distance = abs(unit.x - x) + abs(unit.y - y)
            if distance <= max_range:
                # Skill can target self only if it's a supportive/healing ability
                if distance == 0 and skill_data["type"] != "Heal":
                    continue
                targets.append((x, y))
    return targets

# --- ISOMETRIC TRANSFORMS ---
def iso_to_screen(map_x, map_y, map_z, origin_x, origin_y):
    screen_x = origin_x + (map_x - map_y) * (TILE_WIDTH // 2)
    screen_y = origin_y + (map_x + map_y) * (TILE_HEIGHT // 2) - (map_z * 14) # Scaled step height factor
    return screen_x, screen_y

def draw_iso_tile(surface, sx, sy, height, color):
    h_offset = height * 14
    top_points = [
        (sx, sy),
        (sx + TILE_WIDTH // 2, sy + TILE_HEIGHT // 2),
        (sx, sy + TILE_HEIGHT),
        (sx - TILE_WIDTH // 2, sy + TILE_HEIGHT // 2)
    ]
    if height > 0:
        left_wall = [top_points[3], top_points[2], (top_points[2][0], top_points[2][1] + h_offset), (top_points[3][0], top_points[3][1] + h_offset)]
        pygame.draw.polygon(surface, (int(color[0]*0.5), int(color[1]*0.5), int(color[2]*0.5)), left_wall)
        right_wall = [top_points[2], top_points[1], (top_points[1][0], top_points[1][1] + h_offset), (top_points[2][0], top_points[2][1] + h_offset)]
        pygame.draw.polygon(surface, (int(color[0]*0.7), int(color[1]*0.7), int(color[2]*0.7)), right_wall)

    pygame.draw.polygon(surface, color, top_points)
    draw_tile_texture(surface, top_points, height, color)
    pygame.draw.polygon(surface, GRID_COLOR, top_points, 1)
    return top_points

def draw_unit(surface, sx, sy, unit, is_active=False):
    cx, cy = sx, sy + (TILE_HEIGHT // 2) - 12
    font = pygame.font.SysFont(None, 14)
    tag = "P" if unit.team == "Player" else "E"
    surface.blit(font.render(tag, True, (255, 255, 255)), (cx - 4, cy - 5))

    # Health Profile Bar
    pygame.draw.rect(surface, (200, 50, 50), (cx - 15, cy - 22, 30, 4))
    hp_pct = max(0, unit.hp / unit.max_hp)
    pygame.draw.rect(surface, (50, 200, 50), (cx - 15, cy - 22, int(30 * hp_pct), 4))

    portrait = CHARACTER_PORTRAITS.get(unit.name)
    if portrait:
        portrait_rect = portrait.get_rect(center=(cx, cy))
        surface.blit(portrait, portrait_rect)
        pygame.draw.circle(surface, (255, 255, 255), (cx, cy), 15, 2)
    else:
        pygame.draw.circle(surface, unit.color, (cx, cy), 12)
        pygame.draw.circle(surface, (255, 255, 255), (cx, cy), 12, 2)

    if is_active:
        pygame.draw.polygon(surface, (255, 60, 60), [(cx, cy - 28), (cx - 5, cy - 35), (cx + 5, cy - 35)])


# --- VISUAL HELPER FUNCTIONS ---
def create_portrait_surface(color, label, size=32):
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    base = tuple(max(0, min(255, int(c * 0.8 + 30))) for c in color)
    pygame.draw.rect(surf, base, surf.get_rect(), border_radius=8)
    accent = tuple(max(0, min(255, int(c * 1.1))) for c in color)
    for i in range(2):
        pygame.draw.circle(surf, accent, (size // 2, size // 2), size // 2 - 6 - (i * 8), 2)
    pygame.draw.circle(surf, color, (size // 2, size // 2), size // 2 - 10)
    font = pygame.font.SysFont(None, size // 2)
    letter = font.render(label[0], True, (245, 245, 245))
    surf.blit(letter, letter.get_rect(center=(size // 2, size // 2)))
    return surf


def draw_tile_texture(surface, top_points, height, color):
    pattern_color = tuple(max(0, min(255, c + 30)) for c in color)
    detail_color = tuple(max(0, min(255, c - 40)) for c in color)
    cx = sum(p[0] for p in top_points) / 4
    cy = sum(p[1] for p in top_points) / 4

    if height == 0:
        pygame.draw.circle(surface, pattern_color, (int(cx), int(cy)), 8, 1)
        pygame.draw.line(surface, detail_color, top_points[0], top_points[2], 1)
        pygame.draw.line(surface, detail_color, top_points[1], top_points[3], 1)
        pygame.draw.circle(surface, detail_color, (int(cx), int(cy)), 4, 1)
    elif height == 1:
        pygame.draw.line(surface, pattern_color, top_points[0], top_points[1], 1)
        pygame.draw.line(surface, pattern_color, top_points[1], top_points[2], 1)
        pygame.draw.line(surface, detail_color, top_points[2], top_points[3], 1)
        for offset in [-10, 10]:
            start = (cx + offset, cy - 4)
            end = (cx + offset, cy + 6)
            pygame.draw.line(surface, detail_color, start, end, 1)
    else:
        pygame.draw.line(surface, detail_color, (top_points[0][0] + 8, top_points[0][1] + 6), (top_points[2][0] - 8, top_points[2][1] + 6), 1)
        pygame.draw.line(surface, detail_color, (top_points[1][0] - 8, top_points[1][1] + 6), (top_points[3][0] + 8, top_points[3][1] + 6), 1)
        pygame.draw.circle(surface, pattern_color, (int(cx), int(cy + 2)), 3)


# --- INPUT HELPER FUNCTIONS ---
def point_in_polygon(point, polygon):
    x, y = point
    inside = False
    for i in range(len(polygon)):
        j = (i - 1) % len(polygon)
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-6) + xi)
        if intersect:
            inside = not inside
    return inside


def screen_to_map(mx, my, origin_x, origin_y):
    last_hit = None
    for y in range(MAP_ROWS):
        for x in range(MAP_COLS):
            z = MAP_DATA[y][x]
            sx, sy = iso_to_screen(x, y, z, origin_x, origin_y)
            top_points = [
                (sx, sy),
                (sx + TILE_WIDTH // 2, sy + TILE_HEIGHT // 2),
                (sx, sy + TILE_HEIGHT),
                (sx - TILE_WIDTH // 2, sy + TILE_HEIGHT // 2)
            ]
            if point_in_polygon((mx, my), top_points):
                last_hit = (x, y)
    return last_hit


# --- MAIN ENGINE MODULE ---
def main():
    global MAP_DATA, MAP_ROWS, MAP_COLS, SKILL_REGISTRY, CHARACTER_ROSTER

    required_files = ["map_layout.csv", "skills.csv", "characters.csv"]
    if not all(os.path.exists(filename) for filename in required_files):
        generate_dummy_csv_files()

    MAP_DATA = load_map_from_csv()
    SKILL_REGISTRY = load_skills_from_csv()
    CHARACTER_ROSTER = load_characters_from_csv()
    MAP_ROWS = len(MAP_DATA)
    MAP_COLS = len(MAP_DATA[0]) if MAP_DATA else 0

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Tactics Engine: Data Driven A* Pipeline")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 22)

    origin_x = SCREEN_WIDTH // 2 - 80
    origin_y = SCREEN_HEIGHT // 4

    # Build character entities dynamically from data registry blueprint mapping definitions
    units = [Unit(char_data) for char_data in CHARACTER_ROSTER]
    global CHARACTER_PORTRAITS
    CHARACTER_PORTRAITS = {u.name: create_portrait_surface(u.color, u.name) for u in units}

    game_state = "TICKING" 
    active_unit = None
    
    main_menu = ["Move", "Act", "Wait"]
    current_menu = main_menu
    menu_index = 0
    selected_skill = None
    
    cursor_x, cursor_y = 0, 0
    valid_tiles = []
    combat_log = "System Engine Initialized. Map loaded cleanly."

    running = True
    while running:
        # --- GAME LOGIC: SPEED CT INDEX ENGINE TICKER ---
        if game_state == "TICKING":
            living_units = [u for u in units if u.is_alive()]
            for u in living_units:
                u.ct += u.speed
            
            ready = [u for u in living_units if u.ct >= 100]
            if ready:
                ready.sort(key=lambda u: u.ct, reverse=True)
                active_unit = ready[0]
                active_unit.has_moved = False
                active_unit.has_acted = False
                cursor_x, cursor_y = active_unit.x, active_unit.y
                current_menu = main_menu
                menu_index = 0
                game_state = "MENU"

        # --- INPUT CONTROLLER BINDINGS ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            elif event.type == pygame.KEYDOWN and game_state != "TICKING":
                # UI Menu Browsing States
                if game_state in ["MENU", "SUBMENU_ACT"]:
                    if event.key == pygame.K_UP:    menu_index = (menu_index - 1) % len(current_menu)
                    elif event.key == pygame.K_DOWN:  menu_index = (menu_index + 1) % len(current_menu)
                    elif event.key == pygame.K_ESCAPE:
                        if game_state == "SUBMENU_ACT":
                            current_menu = main_menu
                            menu_index = 1
                            game_state = "MENU"

                    elif event.key == pygame.K_SPACE:
                        choice = current_menu[menu_index]
                        
                        if game_state == "MENU":
                            if choice == "Move" and not active_unit.has_moved:
                                # Trigger clean A* path matrix tracking
                                valid_tiles = get_valid_moves_a_star(active_unit, units)
                                game_state = "MOVE_SELECT"
                            elif choice == "Act" and not active_unit.has_acted:
                                current_menu = active_unit.skills
                                menu_index = 0
                                game_state = "SUBMENU_ACT"
                            elif choice == "Wait":
                                active_unit.ct = 0
                                game_state = "TICKING"
                        
                        elif game_state == "SUBMENU_ACT":
                            skill_name = current_menu[menu_index]
                            skill_rules = SKILL_REGISTRY[skill_name]
                            
                            if active_unit.mp >= skill_rules["mp_cost"]:
                                selected_skill = skill_name
                                valid_tiles = get_skill_targets(active_unit, skill_name)
                                game_state = "TARGET_SELECT"
                            else:
                                combat_log = f"Failed! Requires {skill_rules['mp_cost']} MP."

                # Tactical Grid Target Map Browsing States
                elif game_state in ["MOVE_SELECT", "TARGET_SELECT"]:
                    if event.key == pygame.K_UP and cursor_y > 0: cursor_y -= 1
                    elif event.key == pygame.K_DOWN and cursor_y < MAP_ROWS - 1: cursor_y += 1
                    elif event.key == pygame.K_LEFT and cursor_x > 0: cursor_x -= 1
                    elif event.key == pygame.K_RIGHT and cursor_x < MAP_COLS - 1: cursor_x += 1
                    
                    elif event.key == pygame.K_ESCAPE:
                        cursor_x, cursor_y = active_unit.x, active_unit.y
                        if game_state == "MOVE_SELECT":
                            current_menu = main_menu
                            game_state = "MENU"
                        else:
                            current_menu = active_unit.skills
                            game_state = "SUBMENU_ACT"

                    elif event.key == pygame.K_SPACE:
                        if game_state == "MOVE_SELECT" and (cursor_x, cursor_y) in valid_tiles:
                            active_unit.x, active_unit.y = cursor_x, cursor_y
                            active_unit.has_moved = True
                            current_menu = main_menu
                            menu_index = 0
                            game_state = "MENU"
                        
                        elif game_state == "TARGET_SELECT" and (cursor_x, cursor_y) in valid_tiles:
                            target_unit = next((u for u in units if u.x == cursor_x and u.y == cursor_y and u.is_alive()), None)
                            rules = SKILL_REGISTRY[selected_skill]
                            
                            # Deduct resource parameters
                            active_unit.mp -= rules["mp_cost"]
                            active_unit.tp += 20 if rules["mp_cost"] > 0 else 10
                            
                            if target_unit:
                                dmg = rules["damage"]
                                target_unit.hp = max(0, min(target_unit.max_hp, target_unit.hp - dmg))
                                
                                if dmg >= 0:
                                    combat_log = f"{active_unit.name} uses {selected_skill} on {target_unit.name} for {dmg} damage!"
                                else:
                                    combat_log = f"{active_unit.name} heals {target_unit.name} for {abs(dmg)} HP!"
                                    
                                if not target_unit.is_alive():
                                    combat_log += f" {target_unit.name} was KO'd!"
                            else:
                                combat_log = f"{active_unit.name} casted {selected_skill} but it missed the target field."

                            active_unit.has_acted = True
                            current_menu = main_menu
                            menu_index = 2 
                            game_state = "MENU"

            elif event.type == pygame.MOUSEMOTION and game_state in ["MOVE_SELECT", "TARGET_SELECT"]:
                hit_tile = screen_to_map(event.pos[0], event.pos[1], origin_x, origin_y)
                if hit_tile is not None:
                    cursor_x, cursor_y = hit_tile

            elif event.type == pygame.MOUSEBUTTONDOWN and game_state != "TICKING":
                if event.button == 1:
                    if game_state in ["MENU", "SUBMENU_ACT"]:
                        item_height = 26
                        mx, my = event.pos
                        menu_x, menu_y = 780, 30
                        if menu_x <= mx <= menu_x + 200 and menu_y <= my <= menu_y + 180:
                            relative_y = my - (menu_y + 45)
                            if 0 <= relative_y < len(current_menu) * item_height:
                                clicked_index = relative_y // item_height
                                if clicked_index < len(current_menu):
                                    menu_index = clicked_index
                                    choice = current_menu[menu_index]
                                    if game_state == "MENU":
                                        if choice == "Move" and not active_unit.has_moved:
                                            valid_tiles = get_valid_moves_a_star(active_unit, units)
                                            game_state = "MOVE_SELECT"
                                        elif choice == "Act" and not active_unit.has_acted:
                                            current_menu = active_unit.skills
                                            menu_index = 0
                                            game_state = "SUBMENU_ACT"
                                        elif choice == "Wait":
                                            active_unit.ct = 0
                                            game_state = "TICKING"
                                    elif game_state == "SUBMENU_ACT":
                                        skill_name = current_menu[menu_index]
                                        skill_rules = SKILL_REGISTRY[skill_name]
                                        if active_unit.mp >= skill_rules["mp_cost"]:
                                            selected_skill = skill_name
                                            valid_tiles = get_skill_targets(active_unit, skill_name)
                                            game_state = "TARGET_SELECT"
                                        else:
                                            combat_log = f"Failed! Requires {skill_rules['mp_cost']} MP."

                    elif game_state in ["MOVE_SELECT", "TARGET_SELECT"]:
                        hit_tile = screen_to_map(event.pos[0], event.pos[1], origin_x, origin_y)
                        if hit_tile is not None:
                            cursor_x, cursor_y = hit_tile
                            if game_state == "MOVE_SELECT" and hit_tile in valid_tiles:
                                active_unit.x, active_unit.y = hit_tile
                                active_unit.has_moved = True
                                current_menu = main_menu
                                menu_index = 0
                                game_state = "MENU"
                            elif game_state == "TARGET_SELECT" and hit_tile in valid_tiles:
                                target_unit = next((u for u in units if u.x == cursor_x and u.y == cursor_y and u.is_alive()), None)
                                rules = SKILL_REGISTRY[selected_skill]
                                active_unit.mp -= rules["mp_cost"]
                                active_unit.tp += 20 if rules["mp_cost"] > 0 else 10
                                if target_unit:
                                    dmg = rules["damage"]
                                    target_unit.hp = max(0, min(target_unit.max_hp, target_unit.hp - dmg))
                                    if dmg >= 0:
                                        combat_log = f"{active_unit.name} uses {selected_skill} on {target_unit.name} for {dmg} damage!"
                                    else:
                                        combat_log = f"{active_unit.name} heals {target_unit.name} for {abs(dmg)} HP!"
                                    if not target_unit.is_alive():
                                        combat_log += f" {target_unit.name} was KO'd!"
                                else:
                                    combat_log = f"{active_unit.name} casted {selected_skill} but it missed the target field."
                                active_unit.has_acted = True
                                current_menu = main_menu
                                menu_index = 2
                                game_state = "MENU"

        # --- DRAW VISUAL LAYER PIPELINE ---
        screen.fill(BG_COLOR)

        for x in range(MAP_COLS):
            for y in range(MAP_ROWS):
                z = MAP_DATA[y][x]
                sx, sy = iso_to_screen(x, y, z, origin_x, origin_y)
                
                base_val = 90 + (z * 22)
                tile_color = [base_val, base_val, base_val]

                if game_state == "MOVE_SELECT" and (x, y) in valid_tiles:
                    tile_color = [40, 110, 190] 
                elif game_state == "TARGET_SELECT" and (x, y) in valid_tiles:
                    # Color match tiles dynamically based on skill profile parameters
                    tile_color = list(SKILL_REGISTRY[selected_skill]["color"])

                top_pts = draw_iso_tile(screen, sx, sy, z, tuple(tile_color))

                for u in units:
                    if u.x == x and u.y == y and u.is_alive():
                        draw_unit(screen, sx, sy, u, is_active=(u == active_unit))

                if game_state in ["MOVE_SELECT", "TARGET_SELECT"] and x == cursor_x and y == cursor_y:
                    pygame.draw.polygon(screen, CURSOR_COLOR, top_pts, 3)

        # --- HUD RENDER WRAPPERS ---
        # 1. CT Queue Bar Panel
        pygame.draw.rect(screen, (40, 40, 50), (10, 10, 280, 180))
        pygame.draw.rect(screen, (100, 100, 110), (10, 10, 280, 180), 2)
        screen.blit(font.render("COMBATANT FIELD STATS (CT)", True, (220, 220, 220)), (20, 15))
        
        living_queue = sorted([u for u in units if u.is_alive()], key=lambda u: u.ct, reverse=True)
        for idx, u in enumerate(living_queue):
            col = (100, 180, 255) if u.team == "Player" else (255, 110, 110)
            row_text = f"{u.name:9} HP:{u.hp:3}/{u.max_hp} MP:{u.mp:2} CT:{u.ct}"
            if u == active_unit: row_text += " *"
            screen.blit(font.render(row_text, True, col), (20, 45 + (idx * 24)))

        # 2. Dynamic Command Context Window
        if game_state in ["MENU", "SUBMENU_ACT"] and active_unit:
            mx, my = 780, 30
            pygame.draw.rect(screen, (20, 20, 30), (mx, my, 200, 180))
            pygame.draw.rect(screen, CURSOR_COLOR, (mx, my, 200, 180), 2)
            screen.blit(font.render(f"{active_unit.name} Actions", True, (255, 255, 255)), (mx + 10, my + 10))
            
            portrait = CHARACTER_PORTRAITS.get(active_unit.name)
            if portrait:
                screen.blit(portrait, (mx + 10, my + 120))
                screen.blit(font.render(active_unit.name, True, (200, 200, 255)), (mx + 60, my + 126))
            
            for idx, opt in enumerate(current_menu):
                if (opt == "Move" and active_unit.has_moved) or (opt == "Act" and active_unit.has_acted):
                    opt_color = (70, 70, 70)
                else:
                    opt_color = CURSOR_COLOR if idx == menu_index else (170, 170, 170)
                
                pointer = " -> " if idx == menu_index else "    "
                screen.blit(font.render(f"{pointer}{opt}", True, opt_color), (mx + 5, my + 45 + (idx * 26)))

        # 3. Output Event Log Ticker
        pygame.draw.rect(screen, (15, 15, 25), (10, 630, 980, 60))
        screen.blit(font.render(f"ACTION LOG: {combat_log}", True, (50, 255, 180)), (25, 650))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
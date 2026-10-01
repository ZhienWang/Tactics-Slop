import os
import sys
import math
import heapq
import random
import asyncio
import pygame
import pygame.gfxdraw
from scripts.data_editor import (
    load_escape_tiles_from_csv,
    generate_dummy_csv_files,
    load_map_from_csv,
    load_skills_from_csv,
    load_items_from_csv,
    load_equipment_from_csv,
    load_books_from_csv,
    load_terrain_from_csv,
    load_props_from_csv,
    load_weather_from_csv,
    load_effects_from_csv,
    load_skill_effects_from_csv,
    load_stage_manifest,
    load_settings_from_csv,
    load_dialogues_from_csv,
    load_characters_from_csv,
    generate_terrain_csv,
    generate_map_csv,
    load_terrain_from_text,
    is_water_tile,
    TERRAIN_THEMES,
    STAGE_THEMES,
    BOOK_SLOTS,
)
from scripts.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    TILE_WIDTH,
    TILE_HEIGHT,
    TILE_RISE,
    CURSOR_COLOR,
    FAITH_CAP,
    CLASS_SKILLSETS,
)
from scripts.skybox import Skybox
from scripts.hero import hero_character
from scripts.assets import (
    load_image_safe,
    load_background_image,
    cache_terrain_images,
    cache_terrain_colors,
    build_character_portraits,
    build_character_face_portraits,
    build_character_chess_art,
    build_character_pixel_art,
    build_tree_sprite,
    build_boulder_sprite,
    draw_tile_texture,
    create_projectile_surface,
    bring_window_to_front,
    load_nine_slice_frame,
    draw_nine_slice_panel,
    frame_content_rect,
    get_font,
    terrain_top_face,
)
from scripts.weather import Weather
from scripts.effects import EffectManager, EffectSpec
from scripts.voices import DialogueVoice, MUSIC_VOLUME
from scripts.controls import screen_to_map, tile_corner_offsets, tile_top_points, FLAT_CORNER_OFFSETS

# --- RUNTIME DATA ---
MAP_DATA = []
MAP_ROWS = 0
MAP_COLS = 0
SKILL_REGISTRY = {}
ITEM_REGISTRY = {}
EQUIPMENT_REGISTRY = {}
BOOK_REGISTRY = {}
CHARACTER_ROSTER = []
TERRAIN_LAYOUT = []
# Scenery standing on the map (trees and boulders), and the tiles they occupy -
# a prop owns its whole tile, so nothing can move onto or be shoved into it.
MAP_PROPS = []
PROP_TILES = set()
# Tiles a fleeing unit can escape the battle from (a stage's escape.csv).
ESCAPE_TILES = set()

# A held book's stat gain per the holder's own turn is randomized around 2%
# rather than fixed, since this is a first pass at the balance numbers.
BOOK_STAT_GROWTH_RANGE = (0.015, 0.025)


class Unit:
    def __init__(self, data):
        self.name = data["name"]
        self.team = data["team"]
        self.x = data["x"]
        self.y = data["y"]
        self.speed = data["speed"]
        # A mounted unit rides further each turn (see MOUNTS).
        self.mount = data.get("mount", "")
        self.mv = data["mv"] + MOUNTS.get(self.mount, {}).get("mv", 0)
        self.jump = data["jump"]
        self.max_mp = data["mp"]
        self.mp = data["mp"]
        self.skills = data["skills"]
        self.color = data["color"]
        self.char_class = data.get("class", "")
        self.portrait_path = data.get("portrait_path", "")
        self.ct = 0
        self.tp = 0
        self.has_moved = False
        self.has_acted = False
        self.snared_turns = 0
        self.stunned_turns = 0
        # Turns left unable to act after being Slashed (see DISARM_SKILLS).
        self.disarmed_turns = 0
        # Morale fires at most once per battle and lasts one turn: whether it
        # has been used, and the bonuses currently applied (to take back).
        self.morale_used = False
        self.morale_active = None
        # AI bookkeeping: whether it threw a Fish net on its last turn.
        self.ai_netted_last_turn = False
        # Turns left in Despair (see enter_despair_if_faithless).
        self.despair_turns = 0
        # Shieldbearers take the field with their shields already raised.
        self.guarded = self.char_class in CLASS_STARTS_GUARDED
        # Lead's Love bonus currently granted (0 = not led), and how many
        # more of this unit's turns it lasts (see tick_lead).
        self.lead_bonus = 0
        self.lead_turns = 0
        self.disabled = False
        self.removed = False
        self.removed_at = None
        # Conversion can go back and forth (see convert_unit/turn_back): the
        # side and colour this unit started the battle on, and whether it's
        # currently fighting for the other side. converted_at times the flash.
        self.original_team = self.team
        self.original_color = self.color
        self.original_portrait_path = self.portrait_path
        # A HUD face portrait that overrides the one found from portrait_path
        # - set while a Legionnaire is converted (see convert_unit).
        self.face_portrait_path = data.get("face_portrait") or None
        self.original_face_portrait_path = self.face_portrait_path
        self.convert_face = None
        self.converted = False
        self.converted_at = None
        # Legionnaires who lose their nerve leave the field (see roll_flee).
        self.fled = False
        # Struck to the ground by a scripted scene (see STAGE_SCENES).
        self.fallen = False
        # Short-lived stat buffs from class skills (see add_buff), and turns
        # left during which this unit's faith can't be shaken (Shield of Faith).
        self.buffs = []
        self.faith_ward_turns = 0
        # The player's own character, built from the new-game survey.
        self.is_hero = bool(data.get("hero"))
        self.speech_bubble_until = None
        self.faith_popup = None
        self.magic_attack = data.get("magic_attack", 25)
        self.magic_defense = data.get("magic_defense", 25)
        self.faith = data.get("faith", 25)
        # Level/EXP (see gain_exp): every character starts at Lv 1 unless a
        # characters.csv `level` column says otherwise.
        self.level = data.get("level", 1)
        self.exp = data.get("exp", 0)
        self.exp_popup = None
        self.bravery = data.get("bravery", 25)
        self.patience = data.get("patience", 25)
        self.love = data.get("love", 25)
        # {slot: item_name or None}, set on the world map's Equipment screen
        # and applied once as a flat stat bonus when a battle begins.
        self.equipment = data.get("equipment") or {}
        # Daily Devotion Books, chosen on the world map's Books screen:
        # {slot: book_name or None}, {slot: turns_held}, and {slot: total
        # stat already gained from that slot} - the latter two persist
        # across battles (carried by the world map's roster) so a book's
        # progress survives a fresh Unit being rebuilt at each battle start.
        self.books = data.get("books") or {}
        self.book_turns = data.get("book_turns") or {}
        self.book_gain = data.get("book_gain") or {}

    def is_alive(self):
        return not self.removed


def apply_equipment_bonuses(unit, equipment_registry=None):
    """Adds each equipped item's flat stat bonuses onto a freshly-built
    Unit, once, at battle start - equipment is chosen on the world map's
    Equipment screen, not mid-battle, so there's no un-equip case to
    handle here."""
    registry = equipment_registry if equipment_registry is not None else EQUIPMENT_REGISTRY
    for item_name in unit.equipment.values():
        if not item_name:
            continue
        item = registry.get(item_name)
        if not item:
            continue
        for stat, amount in item["stats"].items():
            if hasattr(unit, stat):
                setattr(unit, stat, getattr(unit, stat) + amount)


def apply_book_bonuses(unit, book_registry=None):
    """Re-applies whatever a unit's books have already grown, once, onto a
    freshly-built Unit at battle start - mirrors apply_equipment_bonuses,
    since book progress (book_gain) is carried on the world map's roster
    but a battle always rebuilds Unit objects from base CSV stats."""
    registry = book_registry if book_registry is not None else BOOK_REGISTRY
    for slot, book_name in unit.books.items():
        if not book_name:
            continue
        book = registry.get(book_name)
        if not book or not hasattr(unit, book["stat"]):
            continue
        gain = unit.book_gain.get(slot, 0)
        if gain:
            setattr(unit, book["stat"], getattr(unit, book["stat"]) + gain)


def apply_book_growth(unit, book_registry=None):
    """Grows the stat tied to each equipped book by a small randomized
    amount (around 2%) once per the unit's own turn, and advances that
    slot's turns-held count its reading level is derived from."""
    registry = book_registry if book_registry is not None else BOOK_REGISTRY
    for slot in BOOK_SLOTS:
        book_name = unit.books.get(slot)
        if not book_name:
            continue
        book = registry.get(book_name)
        if not book or not hasattr(unit, book["stat"]):
            continue
        stat = book["stat"]
        unit.book_turns[slot] = unit.book_turns.get(slot, 0) + 1
        gain = max(1, round(getattr(unit, stat) * random.uniform(*BOOK_STAT_GROWTH_RANGE)))
        setattr(unit, stat, getattr(unit, stat) + gain)
        unit.book_gain[slot] = unit.book_gain.get(slot, 0) + gain


def unit_is_in_water(unit):
    if 0 <= unit.y < len(TERRAIN_LAYOUT) and 0 <= unit.x < len(TERRAIN_LAYOUT[unit.y]):
        return is_water_tile(TERRAIN_LAYOUT[unit.y][unit.x])
    return False


def get_valid_moves_a_star(unit, units_list):
    effective_mv = max(0, unit.mv - 1) if unit_is_in_water(unit) else unit.mv
    start_pos = (unit.x, unit.y)
    open_set = [(0, unit.x, unit.y)]
    g_score = {start_pos: 0}
    occupied_tiles = {(u.x, u.y) for u in units_list if u.is_alive() and u != unit}
    valid_tiles = []

    while open_set:
        cost, cx, cy = heapq.heappop(open_set)
        if cost > effective_mv:
            continue
        if (cx, cy) not in valid_tiles:
            valid_tiles.append((cx, cy))
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < MAP_COLS and 0 <= ny < MAP_ROWS:
                if (nx, ny) in occupied_tiles or (nx, ny) in PROP_TILES:
                    continue
                current_z = MAP_DATA[cy][cx]
                target_z = MAP_DATA[ny][nx]
                if abs(current_z - target_z) <= unit.jump:
                    tentative_g = g_score[(cx, cy)] + 1
                    if tentative_g <= effective_mv and (tentative_g < g_score.get((nx, ny), float('inf'))):
                        g_score[(nx, ny)] = tentative_g
                        heapq.heappush(open_set, (tentative_g, nx, ny))
    return valid_tiles


def get_action_menu(unit, units_list):
    # Only the Player side carries the disciples' satchel of supplies - the
    # Item menu never applies to the Enemy AI.
    menu = ["Move", "Act"]
    if unit.team == "Player":
        menu.append("Item")
    menu.append("Wait")
    return menu


def predict_turn_order(units_list, count=8):
    """Simulates the CT race forward to predict the next `count` units to
    act, in order - not just who currently has the highest CT (which is
    only accurate for the *immediate* next turn, since units gain CT at
    different rates). Doesn't mutate real unit state."""
    living = [u for u in units_list if u.is_alive() and not u.disabled]
    if not living:
        return []
    ct = {u: u.ct for u in living}
    order = []
    for _ in range(min(count, len(living) * 20)):
        ready = [u for u in living if ct[u] >= 100]
        if ready:
            next_unit = max(ready, key=lambda u: (ct[u], u.speed))
        else:
            def turns_needed(u):
                return (100 - ct[u]) / u.speed if u.speed > 0 else float("inf")
            next_unit = min(living, key=lambda u: (turns_needed(u), -u.speed))
            dt = turns_needed(next_unit)
            for u in living:
                ct[u] += u.speed * dt
        order.append(next_unit)
        ct[next_unit] = 0
        if len(order) >= count:
            break
    return order


TURN_QUEUE_ICON_SIZE = 40
TURN_QUEUE_GAP = 6


def draw_turn_order_queue(surface, font, order, portraits, x, y):
    label = font.render("TURN ORDER", True, (220, 220, 220))
    surface.blit(label, (x, y))
    icon_y = y + label.get_height() + 4
    for i, u in enumerate(order):
        icon_x = x + i * (TURN_QUEUE_ICON_SIZE + TURN_QUEUE_GAP)
        rect = pygame.Rect(icon_x, icon_y, TURN_QUEUE_ICON_SIZE, TURN_QUEUE_ICON_SIZE)
        pygame.draw.rect(surface, (20, 20, 30), rect)
        portrait = portraits.get(u.name)
        if portrait:
            fitted = pygame.transform.smoothscale(portrait, (rect.width - 4, rect.height // 2))
            surface.blit(fitted, (rect.x + 2, rect.y + (rect.height - fitted.get_height()) // 2))
        else:
            pygame.draw.circle(surface, u.color, rect.center, rect.width // 2 - 2)
        border_color = (100, 180, 255) if u.team == "Player" else (255, 110, 110)
        pygame.draw.rect(surface, border_color, rect, 3 if i == 0 else 1)


def can_unit_move(unit, units_list):
    return unit.snared_turns == 0 and any(tile != (unit.x, unit.y) for tile in get_valid_moves_a_star(unit, units_list))


def get_skill_targets(unit, skill_name, units_list=None):
    targets = []
    skill_data = SKILL_REGISTRY[skill_name]
    max_range = skill_data["range"]
    for x in range(MAP_COLS):
        for y in range(MAP_ROWS):
            distance = abs(unit.x - x) + abs(unit.y - y)
            if distance <= max_range:
                if distance == 0 and not (skill_data["type"] == "Heal" or skill_name in ("Defend", "Lead")
                                          or skill_name in SELF_CENTRED_SKILLS):
                    continue
                if units_list is not None and any(u.x == x and u.y == y and u.is_alive() and u.disabled for u in units_list):
                    continue  # a disabled unit stands here - not a target
                if skill_name == "Lead" and units_list is not None and not lead_recipients(unit, units_list):
                    continue
                if skill_data["type"] == "Status" and units_list is not None:
                    target = next((u for u in units_list if u.x == x and u.y == y and u.is_alive()), None)
                    if target is None or target.team == unit.team:
                        continue
                if skill_data["type"] == "Support" and units_list is not None:
                    target = next((u for u in units_list if u.x == x and u.y == y and u.is_alive()), None)
                    if target is None or target.team != unit.team:
                        continue
                    if skill_name == "Command" and target == unit:
                        continue
                targets.append((x, y))
    return targets


def get_item_targets(unit, item_name, units_list):
    """Like get_skill_targets, but for consumable items: 'ally' items find a
    living teammate (self included) and 'dead_ally' items (Ankh) find a
    fallen teammate at the tile where they were struck down."""
    targets = []
    item_data = ITEM_REGISTRY[item_name]
    max_range = item_data["range"]
    wants_dead = item_data["target_scope"] == "dead_ally"
    for x in range(MAP_COLS):
        for y in range(MAP_ROWS):
            distance = abs(unit.x - x) + abs(unit.y - y)
            if distance > max_range:
                continue
            occupant = next(
                (u for u in units_list if u.x == x and u.y == y and u.team == unit.team and u.is_alive() != wants_dead
                 and not u.disabled),
                None,
            )
            if occupant is not None:
                targets.append((x, y))
    return targets


def find_item_target(units_list, x, y, item_name, team):
    item_data = ITEM_REGISTRY[item_name]
    wants_dead = item_data["target_scope"] == "dead_ally"
    return next(
        (u for u in units_list if u.x == x and u.y == y and u.team == team and u.is_alive() != wants_dead
         and not u.disabled),
        None,
    )


SHOVE_CHANCE = 0.5
SHOVE_DISTANCE = 2
COMMAND_CT_BOOST = 40


def push_unit_away(caster, target, units_list, tiles=SHOVE_DISTANCE):
    dx = target.x - caster.x
    dy = target.y - caster.y
    if dx == 0 and dy == 0:
        return
    if abs(dx) >= abs(dy):
        step = (1 if dx > 0 else -1, 0)
    else:
        step = (0, 1 if dy > 0 else -1)
    occupied = {(u.x, u.y) for u in units_list if u.is_alive() and u != target} | PROP_TILES
    x, y = target.x, target.y
    for _ in range(tiles):
        nx, ny = x + step[0], y + step[1]
        if not (0 <= nx < MAP_COLS and 0 <= ny < MAP_ROWS) or (nx, ny) in occupied:
            break
        x, y = nx, ny
    target.x, target.y = x, y


DEATH_FADE_MS = 500
CONVERT_FLASH_MS = 700


def draw_conversion_flash(surface, cx, cy, elapsed, duration=CONVERT_FLASH_MS):
    progress = max(0.0, min(1.0, elapsed / duration))
    radius = int(14 + progress * 34)
    alpha = max(0, 255 - int(255 * progress))
    ring = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
    pygame.draw.circle(ring, (255, 215, 0, alpha), (radius + 2, radius + 2), radius, 3)
    surface.blit(ring, (cx - radius - 2, cy - radius - 2))


# Preach plays out as a beat, not an instant number change: its particle
# effect plays for PREACH_BUBBLE_MS, then the actual Faith gain floats up off
# the target for FAITH_POPUP_MS. Items still show a "talking" speech bubble
# on both units for that first beat.
PREACH_BUBBLE_MS = 700
FAITH_POPUP_MS = 900


def draw_speech_bubble(surface, cx, cy, zoom=1.0):
    width, height = round(34 * zoom), round(22 * zoom)
    bubble_rect = pygame.Rect(0, 0, width, height)
    bubble_rect.center = (cx, cy)
    pygame.draw.ellipse(surface, (250, 250, 245), bubble_rect)
    pygame.draw.ellipse(surface, (40, 40, 40), bubble_rect, 2)
    tail = [
        (cx - round(5 * zoom), bubble_rect.bottom - round(3 * zoom)),
        (cx + round(3 * zoom), bubble_rect.bottom - round(3 * zoom)),
        (cx - round(2 * zoom), bubble_rect.bottom + round(9 * zoom)),
    ]
    pygame.draw.polygon(surface, (250, 250, 245), tail)
    pygame.draw.polygon(surface, (40, 40, 40), tail, 1)
    font = get_font(max(10, round(18 * zoom)))
    dots = font.render("...", True, (40, 40, 40))
    surface.blit(dots, dots.get_rect(center=bubble_rect.center))


def draw_exp_popup(surface, cx, cy, popup, elapsed):
    """'+12 EXP' rising over the actor, with LEVEL UP! above it on a level."""
    progress = max(0.0, min(1.0, elapsed / EXP_POPUP_MS))
    rise = round(24 * progress)
    alpha = max(0, 255 - int(255 * progress ** 2))

    def outlined(font, label, color, center):
        # A dark outline keeps it readable over bright effects and terrain.
        shadow = font.render(label, True, (15, 15, 25))
        shadow.set_alpha(alpha)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)):
            surface.blit(shadow, shadow.get_rect(center=(center[0] + dx, center[1] + dy)))
        text = font.render(label, True, color)
        text.set_alpha(alpha)
        surface.blit(text, text.get_rect(center=center))

    outlined(get_font(24), f"+{popup['amount']} EXP", (150, 215, 255), (cx, cy - rise))
    if popup["levels"]:
        label = "LEVEL UP!" if popup["levels"] == 1 else f"LEVEL UP x{popup['levels']}!"
        outlined(get_font(30, bold=True), label, (255, 225, 90), (cx, cy - rise - 22))


def draw_faith_popup(surface, cx, cy, amount, elapsed, duration=FAITH_POPUP_MS):
    progress = max(0.0, min(1.0, elapsed / duration))
    rise = round(30 * progress)
    alpha = max(0, 255 - int(255 * progress))
    font = get_font(24)
    sign = "+" if amount >= 0 else ""
    color = (255, 215, 0) if amount >= 0 else (255, 90, 90)
    text = font.render(f"{sign}{amount} Faith", True, color)
    text.set_alpha(alpha)
    surface.blit(text, text.get_rect(center=(cx, cy - rise)))


def kill_unit(target):
    target.removed = True
    target.removed_at = pygame.time.get_ticks()


PHYSICAL_BASE_HIT_CHANCE = 0.85
ELEVATION_HIT_BONUS_PER_TILE = 0.08
PHYSICAL_MIN_HIT_CHANCE = 0.5
PHYSICAL_MAX_HIT_CHANCE = 0.98


def tile_elevation(x, y):
    if 0 <= y < len(MAP_DATA) and 0 <= x < len(MAP_DATA[y]):
        return MAP_DATA[y][x]
    return 0


# Job/class passives: each class fights a little differently rather than
# sharing one generic statline, per FFT/Tactics Ogre convention.
CLASS_HIT_BONUS = {"Soldier": 0.05, "Sergeant": 0.05}
CLASS_IGNORES_UPHILL_PENALTY = {"Archer"}
CLASS_PREACH_MULTIPLIER = {"Missionary": 1.5}
CLASS_SHOVE_DISTANCE = {"Sergeant": 3}
# Legionnaire subclasses: Archers shoot from range (above), Shieldbearers
# hold the line - they start each battle guarded and are harder to land a
# Physical hit on - and Medics keep the ranks steady with Rally.
CLASS_STARTS_GUARDED = {"Shieldbearer"}
CLASS_HIT_PENALTY_AGAINST = {"Shieldbearer": 0.15}
OFFICER_AURA_CLASS = "Officer"
OFFICER_AURA_RANGE = 2
OFFICER_AURA_HIT_BONUS = 0.1


def officer_aura_bonus(attacker, units_list):
    """Officers steady nearby troops, granting allies within command range
    a hit-chance bonus."""
    if not units_list:
        return 0.0
    for u in units_list:
        if (
            u is not attacker
            and u.team == attacker.team
            and u.char_class == OFFICER_AURA_CLASS
            and u.is_alive()
            and abs(u.x - attacker.x) + abs(u.y - attacker.y) <= OFFICER_AURA_RANGE
        ):
            return OFFICER_AURA_HIT_BONUS
    return 0.0


MAGIC_DEFENSE_HIT_SCALE = 0.002


def physical_hit_chance(attacker, target, units_list=None):
    """Attacking from higher ground is easier to land; attacking uphill is
    harder - elevation previously had no effect on combat at all beyond
    how far a unit could see/reach. A staple of the genre (Final Fantasy
    Tactics, Tactics Ogre). Archers are trained to compensate for uphill
    shots and never suffer the elevation penalty (though they still enjoy
    the bonus of high ground). Soldiers/Sergeants fight with steadier aim,
    and any Officer nearby further steadies their allies' hand. The
    target's Resist (their armor, per the equipment catalog's helmet/
    breastplate/greaves flavor) makes them harder to hit in turn."""
    elevation_diff = tile_elevation(attacker.x, attacker.y) - tile_elevation(target.x, target.y)
    if attacker.char_class in CLASS_IGNORES_UPHILL_PENALTY:
        elevation_diff = max(0, elevation_diff)
    chance = PHYSICAL_BASE_HIT_CHANCE + elevation_diff * ELEVATION_HIT_BONUS_PER_TILE
    chance += CLASS_HIT_BONUS.get(attacker.char_class, 0.0)
    chance += officer_aura_bonus(attacker, units_list)
    chance -= target.magic_defense * MAGIC_DEFENSE_HIT_SCALE
    chance -= CLASS_HIT_PENALTY_AGAINST.get(target.char_class, 0.0)
    return max(PHYSICAL_MIN_HIT_CHANCE, min(PHYSICAL_MAX_HIT_CHANCE, chance))


# Morale: at the start of each of its turns a unit rolls for a surge of
# morale - a base dice roll everyone gets, plus Bravery on top. It can fire
# only once per battle, and the bonus lasts just that one turn (taken back
# at the start of the unit's next turn).
MORALE_BASE_CHANCE = 0.05
MORALE_CHANCE_SCALE = 0.004
MORALE_CHANCE_CAP = 0.35
MORALE_FAITH_BONUS = 5
MORALE_MV_BONUS = 1
MORALE_JUMP_BONUS = 1
MORALE_SPEED_BONUS = 5


def morale_buff_chance(unit):
    """Bravery's role: a chance, once per this unit's own turn, to catch a
    surge of morale - capped well short of certainty so it stays a nice
    bonus rather than something to build a whole strategy around."""
    return min(MORALE_CHANCE_CAP, MORALE_BASE_CHANCE + unit.bravery * MORALE_CHANCE_SCALE)


# --- Leveling (Final Fantasy Tactics style) ---
# Every action a unit performs on a target - hit or miss, skill or item -
# earns EXP_BASE + (target's level - actor's level), kept within
# EXP_MIN..EXP_MAX, so acting on stronger units teaches more. The action
# that fills an enemy's faith to the cap - converting them - earns
# CONVERT_EXP_BASE + CONVERT_EXP_PER_LEVEL per level of difference instead,
# kept within CONVERT_EXP_MIN..CONVERT_EXP_MAX. Each EXP_PER_LEVEL EXP is a
# level (the rest carries over), up to MAX_LEVEL. Enemies level up the same
# way.
EXP_BASE = 11
EXP_MIN, EXP_MAX = 9, 15
CONVERT_EXP_BASE = 55
CONVERT_EXP_PER_LEVEL = 2
CONVERT_EXP_MIN, CONVERT_EXP_MAX = 45, 65
EXP_PER_LEVEL = 100
MAX_LEVEL = 99
# Stats gained per level, by job. Fixed rather than random so a unit's
# stats can be rebuilt exactly from its level (apply_level_bonuses), the
# same way equipment and book bonuses are re-applied each battle.
LEVEL_GROWTH = {
    "Missionary": {"max_mp": 5, "magic_attack": 2, "magic_defense": 1},
    "Apostle": {"max_mp": 3, "magic_attack": 1, "magic_defense": 1},
    "Soldier": {"max_mp": 1, "magic_attack": 1, "magic_defense": 2},
    "Sergeant": {"max_mp": 1, "magic_attack": 1, "magic_defense": 2},
    "Officer": {"max_mp": 2, "magic_attack": 1, "magic_defense": 2},
    "Archer": {"max_mp": 1, "magic_attack": 1, "magic_defense": 1},
    "Shieldbearer": {"max_mp": 1, "magic_attack": 0, "magic_defense": 3},
    "Medic": {"max_mp": 2, "magic_attack": 2, "magic_defense": 1},
}
DEFAULT_LEVEL_GROWTH = {"max_mp": 2, "magic_attack": 1, "magic_defense": 1}
# Speed grows slowly, as in FFT: +1 on every Nth level.
SPEED_GROWTH_EVERY = 5
EXP_POPUP_MS = 1400


def exp_for_action(actor, target, outcome="hit"):
    """EXP for one action. `outcome` "convert" means this action was the one
    that brought an enemy's faith to the cap."""
    level_gap = (target.level if target is not None else actor.level) - actor.level
    if outcome == "convert":
        return max(CONVERT_EXP_MIN, min(CONVERT_EXP_MAX, CONVERT_EXP_BASE + CONVERT_EXP_PER_LEVEL * level_gap))
    return max(EXP_MIN, min(EXP_MAX, EXP_BASE + level_gap))


def grow_one_level(unit, new_level):
    """The stat gains for reaching `new_level`."""
    for stat, amount in LEVEL_GROWTH.get(unit.char_class, DEFAULT_LEVEL_GROWTH).items():
        setattr(unit, stat, getattr(unit, stat) + amount)
        if stat == "max_mp":
            unit.mp += amount
    if new_level % SPEED_GROWTH_EVERY == 0:
        unit.speed += 1


def apply_level_bonuses(unit):
    """Re-applies the growth for every level past 1 onto a freshly built
    Unit (whose stats come from characters.csv as its Lv 1 base)."""
    for level in range(2, unit.level + 1):
        grow_one_level(unit, level)


def gain_exp(unit, amount):
    """Adds EXP, levelling up for every EXP_PER_LEVEL. Returns how many
    levels were gained."""
    if unit.level >= MAX_LEVEL:
        unit.exp = min(unit.exp + amount, EXP_PER_LEVEL - 1)
        return 0
    unit.exp += amount
    gained = 0
    while unit.exp >= EXP_PER_LEVEL and unit.level < MAX_LEVEL:
        unit.exp -= EXP_PER_LEVEL
        unit.level += 1
        grow_one_level(unit, unit.level)
        gained += 1
    if unit.level >= MAX_LEVEL:
        unit.exp = min(unit.exp, EXP_PER_LEVEL - 1)
    return gained


def award_action_exp(actor, target, outcome="hit"):
    """EXP for `actor` performing an action on `target`; shows the gain (and
    any level up) over the actor. Returns (exp, levels gained)."""
    amount = exp_for_action(actor, target, outcome)
    levels = gain_exp(actor, amount)
    # Shown just after the action's own speech bubble/faith popup.
    actor.exp_popup = {"amount": amount, "levels": levels, "start": pygame.time.get_ticks() + PREACH_BUBBLE_MS}
    if levels:
        queue_effect("@level_up", actor, actor)
    return amount, levels


def report_action(trigger, actor, target, outcome="hit", recipients=None):
    """An Act or item was performed: award its EXP and queue its effects.
    Called exactly once per action, from wherever it resolves."""
    # Announced before the EXP award, so a level-up banner follows the act.
    announce_skill(trigger, actor)
    if actor is not None:
        award_action_exp(actor, target, outcome)
    queue_effect(trigger, actor, target, outcome, recipients, announce=False)


# Particle effects: game rules report what happened here, and the battle
# loop plays whichever effects data/skill_effects.csv binds to it (see
# play_queued_effects). `trigger` is a skill or item name, or an '@event';
# `outcome` is hit / miss / blocked / convert / shaken / despair.
EFFECT_EVENTS = []

# Skill-name banners: every act, item and triggered buff/status is announced
# at the top of the screen, one at a time, FFT style. '@events' are shown by
# the names below; anything else is a skill or item and shows its own name.
SKILL_BANNERS = []
EVENT_BANNER_NAMES = {
    "@morale": "Morale Surge",
    "@rekindle": "Rekindle",
    "@lead_fade": "Lead Fades",
    "@despair_turn": "Despair",
    "@stunned": "Stunned",
    "@snared": "Snared",
    "@level_up": "Level Up!",
    "@disarmed": "Disarmed",
    "@turned_back": "Turned Back",
    "@fled": "Fled!",
    "@escaped": "Escaped!",
    "@heavenly_light": "A Light from Heaven",
}
SKILL_BANNER_MS = 1200
# With more banners waiting, each is shown for less time so they keep up.
SKILL_BANNER_RUSHED_MS = 700
SKILL_BANNER_FADE_MS = 150


def announce_skill(trigger, unit):
    if not trigger:
        return
    name = EVENT_BANNER_NAMES.get(trigger, trigger.lstrip("@").replace("_", " ").title() if trigger.startswith("@") else trigger)
    SKILL_BANNERS.append({"name": name, "unit": unit.name if unit else "", "team": unit.team if unit else None, "start": None})


def draw_skill_banner(surface, font, center_x, top):
    """Shows the oldest waiting skill banner, dropping it once its time is
    up so the next one takes its place."""
    now = pygame.time.get_ticks()
    while SKILL_BANNERS:
        banner = SKILL_BANNERS[0]
        if banner["start"] is None:
            banner["start"] = now
        duration = SKILL_BANNER_RUSHED_MS if len(SKILL_BANNERS) > 1 else SKILL_BANNER_MS
        if now - banner["start"] < duration:
            break
        SKILL_BANNERS.pop(0)
    if not SKILL_BANNERS:
        return
    banner = SKILL_BANNERS[0]
    elapsed = now - banner["start"]
    duration = SKILL_BANNER_RUSHED_MS if len(SKILL_BANNERS) > 1 else SKILL_BANNER_MS
    alpha = round(255 * max(0.0, min(1.0, elapsed / SKILL_BANNER_FADE_MS, (duration - elapsed) / SKILL_BANNER_FADE_MS)))

    title_font = get_font(34, bold=True)
    title = title_font.render(banner["name"], True, (255, 236, 170))
    subtitle = font.render(banner["unit"], True, (200, 200, 210)) if banner["unit"] else None
    width = max(title.get_width(), subtitle.get_width() if subtitle else 0) + 80
    height = title.get_height() + (subtitle.get_height() + 2 if subtitle else 0) + 16
    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    panel.fill((16, 16, 26, 215))
    edge = (100, 180, 255) if banner["team"] == "Player" else (255, 110, 110) if banner["team"] else CURSOR_COLOR
    pygame.draw.line(panel, edge, (0, 0), (width, 0), 3)
    pygame.draw.line(panel, edge, (0, height - 1), (width, height - 1), 3)
    panel.blit(title, ((width - title.get_width()) // 2, 8))
    if subtitle:
        panel.blit(subtitle, ((width - subtitle.get_width()) // 2, 8 + title.get_height() + 2))
    panel.set_alpha(alpha)
    surface.blit(panel, (center_x - width // 2, top))


def queue_effect(trigger, caster, target, outcome="hit", recipients=None, announce=True):
    if not trigger:
        return
    if announce:
        announce_skill(trigger, caster)
    EFFECT_EVENTS.append({
        "trigger": trigger,
        "outcome": outcome,
        "caster": (caster.x, caster.y) if caster else None,
        "target": (target.x, target.y) if target else None,
        "recipients": [(u.x, u.y) for u in recipients] if recipients else [],
    })


def apply_morale_buff(unit):
    """Rolls for this battle's one morale surge; on a hit, boosts Faith,
    Move, Jump and Speed for this turn only (end_morale_buff takes them back
    next turn). Returns whether it triggered."""
    if unit.morale_used or random.random() >= morale_buff_chance(unit):
        return False
    unit.morale_used = True
    faith_gain = min(MORALE_FAITH_BONUS, FAITH_CAP - unit.faith)
    unit.morale_active = {"faith": faith_gain, "mv": MORALE_MV_BONUS, "jump": MORALE_JUMP_BONUS, "speed": MORALE_SPEED_BONUS}
    for stat, amount in unit.morale_active.items():
        setattr(unit, stat, getattr(unit, stat) + amount)
    queue_effect("@morale", unit, unit)
    return True


def end_morale_buff(unit):
    """Takes back last turn's morale bonus, if any. Returns whether it did."""
    if not unit.morale_active:
        return False
    for stat, amount in unit.morale_active.items():
        setattr(unit, stat, max(0, getattr(unit, stat) - amount))
    unit.morale_active = None
    return True


# Slash doesn't kill: it disarms the target, who then can't act (use Acts
# or items) for their next DISARM_TURNS turns - they can still move. Other
# Physical skills (Shoot) still strike the target down.
DISARM_SKILLS = {"Slash", "Sling"}
DISARM_TURNS = 2


def tick_disarm(unit):
    """Called at the start of a unit's turn: if disarmed, spends one of its
    disarmed turns and blocks acting this turn. Returns whether it's
    disarmed this turn."""
    if unit.disarmed_turns <= 0:
        return False
    unit.disarmed_turns -= 1
    unit.has_acted = True
    queue_effect("@disarmed", unit, unit)
    return True


def resolve_physical_hit(attacker, target, skill_name, units_list=None):
    """Resolve a Physical-type skill's hit on a target. May miss outright
    (see physical_hit_chance); otherwise a guarded target blocks it
    (consuming the guard) instead of being removed. Returns
    (killed, message)."""
    if random.random() >= physical_hit_chance(attacker, target, units_list):
        report_action(skill_name, attacker, target, "miss")
        return False, f"{attacker.name}'s {skill_name} misses {target.name}!"
    if target.guarded:
        target.guarded = False
        report_action(skill_name, attacker, target, "blocked")
        return False, f"{target.name} guards against {attacker.name}'s {skill_name} and holds their ground!"
    report_action(skill_name, attacker, target, "hit")
    if skill_name in DISARM_SKILLS:
        target.disarmed_turns = DISARM_TURNS
        return False, f"{attacker.name} disarms {target.name} with {skill_name} - they can't act for {DISARM_TURNS} turns!"
    kill_unit(target)
    return True, f"{attacker.name} strikes down {target.name} with {skill_name}!"


def skill_status_message(skill_name, caster, target):
    if skill_name in SIGNATURE_SKILLS:
        return LAST_SIGNATURE_LOG
    if skill_name == "Shove":
        return f"{caster.name} shoves {target.name} back, leaving them reeling!"
    if skill_name == "Command":
        return f"{caster.name} commands {target.name}, hastening them into action!"
    if skill_name == "Lead":
        return f"{caster.name} leads the way - believers nearby take heart! (+{LEAD_LOVE_BONUS} Love)"
    if skill_name == "Rally":
        return f"{caster.name} rallies {target.name} - their doubts fade and they're steady again!"
    if skill_name == "Defend":
        if caster == target:
            return f"{caster.name} braces and stands firm, ready to guard!"
        return f"{caster.name} calls {target.name} to stand firm and guard!"
    return f"{caster.name} snares {target.name} with Fish net for 2 turns!"


PATIENCE_RESIST_SCALE = 0.004
PATIENCE_RESIST_CAP = 0.6


def status_resist_chance(target):
    """A patient unit has a chance to simply shrug off a hostile status
    effect (Snare, Stun) rather than suffer it - capped well short of
    certainty so even a very patient unit can still be caught out."""
    return min(PATIENCE_RESIST_CAP, target.patience * PATIENCE_RESIST_SCALE)


# Lead (Paul's): every friendly unit within LEAD_RADIUS tiles of the leader
# - the leader included - gains LEAD_LOVE_BONUS Love for its next
# LEAD_TURNS turns. Love drives Faith-attack accuracy (faith_hit_chance),
# so a led band of believers preaches far more surely. Leading a unit
# that's already led refreshes its turns rather than stacking the bonus.
LEAD_RADIUS = 2
LEAD_LOVE_BONUS = 50
LEAD_TURNS = 3


def lead_recipients(leader, units_list):
    return [
        u for u in units_list
        if targetable(u) and u.team == leader.team
        and abs(u.x - leader.x) + abs(u.y - leader.y) <= LEAD_RADIUS
    ]


def tick_lead(unit):
    """Called at the start of a unit's turn. While led, spends one of its
    led turns; once all LEAD_TURNS are spent, the next turn start takes the
    Love bonus back. Returns whether the bonus just wore off."""
    if not unit.lead_bonus:
        return False
    if unit.lead_turns > 0:
        unit.lead_turns -= 1
        return False
    unit.love -= unit.lead_bonus
    unit.lead_bonus = 0
    queue_effect("@lead_fade", unit, unit)
    return True


def apply_skill_status(skill_name, caster, target, units_list):
    """Applies a Status/Support skill; returns whether it took effect."""
    if skill_name in SIGNATURE_SKILLS:
        return resolve_signature(skill_name, caster, target, units_list)
    recipients = lead_recipients(caster, units_list or [caster]) if skill_name == "Lead" else None
    landed = _resolve_skill_status(skill_name, caster, target, units_list)
    report_action(skill_name, caster, target, "hit" if landed else "miss", recipients)
    return landed


def _resolve_skill_status(skill_name, caster, target, units_list):
    if skill_name == "Fish net":
        if random.random() < status_resist_chance(target):
            return False
        target.snared_turns = 2
        return True
    if skill_name == "Shove":
        if random.random() >= SHOVE_CHANCE:
            return False
        if random.random() < status_resist_chance(target):
            return False
        target.stunned_turns = 1
        push_unit_away(caster, target, units_list, tiles=CLASS_SHOVE_DISTANCE.get(caster.char_class, SHOVE_DISTANCE))
        return True
    if skill_name == "Command":
        target.ct = min(100, target.ct + COMMAND_CT_BOOST)
        return True
    if skill_name == "Defend":
        target.guarded = True
        return True
    if skill_name == "Rally":
        return apply_rally(target)
    if skill_name == "Lead":
        recipients = lead_recipients(caster, units_list or [caster])
        for unit in recipients:
            if not unit.lead_bonus:
                unit.love += LEAD_LOVE_BONUS
                unit.lead_bonus = LEAD_LOVE_BONUS
            unit.lead_turns = LEAD_TURNS
        return bool(recipients)
    return False


# Rally (the Legionnaire Medic's heal): an enemy's "wounds" are the faith
# the Player's preaching has built up in them, so Rally talks an ally back
# round - pulling their faith down toward RALLY_BASELINE_FAITH (where every
# enemy starts), never below it - and clears Stun, Snare and Disarm.
RALLY_FAITH_RESTORE = 20
RALLY_BASELINE_FAITH = 100


def rally_need(target):
    """(faith Rally would change, whether it would clear a status). On the
    Player side - a converted Medic rallying its new allies - faith is
    health, so Rally raises it instead."""
    if target.team == "Player":
        excess = max(0, min(RALLY_FAITH_RESTORE, FAITH_CAP - target.faith))
    else:
        excess = max(0, min(RALLY_FAITH_RESTORE, target.faith - RALLY_BASELINE_FAITH))
    statused = target.stunned_turns > 0 or target.snared_turns > 0 or target.disarmed_turns > 0
    return excess, statused


def apply_rally(target):
    """Returns whether Rally changed anything."""
    excess, statused = rally_need(target)
    change = excess if target.team == "Player" else -excess
    target.faith += change
    target.stunned_turns = target.snared_turns = target.disarmed_turns = 0
    if excess:
        target.faith_popup = {"amount": round(change), "start": pygame.time.get_ticks()}
    return bool(excess or statused)


# Conversion: an enemy preached to FAITH_CAP joins the Player side and fights
# for it under the player's control. A convert whose faith is then shaken
# all the way to 0 turns back to its original side (instead of falling into
# Despair), and can be preached over again - back and
# forth until every enemy has converted or fled. Either way the unit starts
# over on its new side with a young faith of SIDE_SWITCH_FAITH.
SIDE_SWITCH_FAITH = 100
CONVERTED_COLOR = (70, 140, 255)


# Art a converted unit switches to, by its regular portrait_path (see
# assets/converted_art.py). Units not listed keep their own art.
CONVERTED_PORTRAIT_PATHS = {"assets/legionaire.png": "assets/legionaire_converted.png"}
# Converted Legionnaires each get a commoner's face for the HUD, drawn at
# random from these public-domain paintings (see its CREDITS.txt) - no two
# alike in a battle while there are faces to spare, and a unit keeps its
# face if it turns back and is converted again. Faces handed out this battle
# are tracked in CONVERT_FACES_USED (cleared when a battle starts).
CONVERT_FACE_DIR = "assets/portraits/converts"
CONVERT_FACES_USED = set()


def convert_face_paths():
    try:
        names = sorted(f for f in os.listdir(CONVERT_FACE_DIR) if f.lower().endswith(".png"))
    except OSError:
        return []
    return [f"{CONVERT_FACE_DIR}/{name}" for name in names]


def pick_convert_face():
    faces = convert_face_paths()
    unused = [f for f in faces if f not in CONVERT_FACES_USED]
    if not (unused or faces):
        return None
    face = random.choice(unused or faces)
    CONVERT_FACES_USED.add(face)
    return face


def convert_unit(unit, team, flash_at):
    unit.team = team
    unit.color = CONVERTED_COLOR
    unit.portrait_path = CONVERTED_PORTRAIT_PATHS.get(unit.original_portrait_path, unit.original_portrait_path)
    if is_legionnaire(unit):
        if unit.convert_face is None:
            unit.convert_face = pick_convert_face()
        unit.face_portrait_path = unit.convert_face
    unit.converted = True
    unit.converted_at = flash_at
    unit.faith = SIDE_SWITCH_FAITH
    # A fresh start on the new side: no lingering enemy statuses or guard.
    unit.stunned_turns = unit.snared_turns = unit.disarmed_turns = 0
    unit.guarded = False


def turn_back(unit, flash_at):
    unit.team = unit.original_team
    unit.color = unit.original_color
    unit.portrait_path = unit.original_portrait_path
    unit.face_portrait_path = unit.original_face_portrait_path
    unit.converted = False
    unit.converted_at = flash_at
    unit.faith = SIDE_SWITCH_FAITH
    unit.despair_turns = 0
    unit.faith_popup = {"amount": round(unit.faith), "start": flash_at}
    queue_effect("@turned_back", unit, unit)


# Fleeing: at the start of each of its turns a Legionnaire still on the enemy
# side rolls to flee the field. Nobody runs while the line holds - the chance
# grows with the share of the original enemy force already converted or fled
# - and courage (Bravery + Patience) holds a soldier in place.
FLEE_MAX_CHANCE = 0.6
FLEE_COURAGE_SCALE = 150


def is_legionnaire(unit):
    return unit.name.startswith("Legionnaire")


def flee_chance(unit, units_list):
    if not is_legionnaire(unit) or unit.team != unit.original_team or not units_list:
        return 0.0
    force = [u for u in units_list if u.original_team == unit.original_team]
    lost = sum(1 for u in force if u.fled or u.team != u.original_team)
    pressure = lost / len(force)
    timidity = max(0.0, 1 - (unit.bravery + unit.patience) / FLEE_COURAGE_SCALE)
    return FLEE_MAX_CHANCE * pressure * timidity


def roll_flee(unit, units_list):
    """Returns whether the unit just fled the battle."""
    if random.random() >= flee_chance(unit, units_list):
        return False
    queue_effect("@fled", unit, unit)
    unit.fled = True
    kill_unit(unit)
    return True


# Escaping: on stages with exit tiles (escape.csv), units of an escaping
# class - the Damascus road's disciples - spend their turns running for the
# exits instead of fighting, and leave the battle for good once they reach
# one. Each turn a disciple may instead stand firm and witness (act as
# usual) with a chance of its Bravery / 100 - unless an exit is in reach, in
# which case it always goes. The player stops them by netting them (a
# snared unit can't run), blocking the road, or converting them first.
ESCAPING_CLASSES = {"Disciple"}


def distance_to_escape(tile):
    return min(abs(tile[0] - x) + abs(tile[1] - y) for x, y in ESCAPE_TILES)


def plan_escape(unit, units_list, snared=False):
    """Where an escaping unit runs to this turn - {"tile", "escapes"} - or
    None if it doesn't run (it then acts or advances as usual)."""
    if (not ESCAPE_TILES or unit.char_class not in ESCAPING_CLASSES or unit.team != unit.original_team
            or snared or unit.snared_turns > 0 or unit.has_moved):
        return None
    reachable = get_valid_moves_a_star(unit, units_list)
    exits = [tile for tile in reachable if tile in ESCAPE_TILES]
    if exits:
        return {"tile": min(exits, key=lambda t: abs(t[0] - unit.x) + abs(t[1] - unit.y)), "escapes": True}
    if random.random() < unit.bravery / 100 and choose_ai_action(unit, units_list)["action"] == "skill":
        return None
    best = min(reachable, key=lambda t: (distance_to_escape(t), abs(t[0] - unit.x) + abs(t[1] - unit.y)))
    if distance_to_escape(best) >= distance_to_escape((unit.x, unit.y)):
        return None  # hemmed in - no closer to an exit, so it stands and acts
    return {"tile": best, "escapes": False}


def carry_out_escape(unit, plan):
    """Moves the unit per plan_escape; returns the combat log line."""
    unit.x, unit.y = plan["tile"]
    unit.has_moved = True
    if not plan["escapes"]:
        return f"{unit.name} runs for the road to Damascus!"
    queue_effect("@escaped", unit, unit)
    unit.fled = True
    kill_unit(unit)
    return f"{unit.name} escapes down the road to Damascus!"


# Scripted scenes: once only `enemies_left` enemies still stand against the
# player on a stage, the battle stops for a scene - a light from heaven on
# Paul that throws him to the ground (Acts 9:3-4), then the dialogue lines
# filed under `dialogue` in dialogues.csv - and the stage ends with the
# scene's own title and closing line instead of the usual victory.
STAGE_SCENES = {
    "damascus": {
        "enemies_left": 2,
        "dialogue": "light",
        "title": "A LIGHT FROM HEAVEN",
        "subtitle": "Saul rises blind, and his men lead him by the hand into Damascus.",
    },
}
# Shown on the end screen once the demo has been played through (its
# ending scene, or any victory) - this build stops after the opening stage.
DEMO_THANKS = "Thank you for playing the demo!"
DEMO_THANKS_DETAIL = "The rest of the road to Jerusalem is still being walked - more is coming soon."

# How long the light shines before the voice speaks, and how long its
# first blinding flash lasts.
SCENE_LIGHT_MS = 2600
SCENE_FLASH_MS = 900


def enemies_standing(units):
    return [u for u in units if u.is_alive() and u.team != "Player"]


def scene_due(stage_id, units):
    scene = STAGE_SCENES.get(stage_id)
    return bool(scene) and len(enemies_standing(units)) <= scene["enemies_left"]


def strike_down(unit):
    """The light from heaven: the unit falls to the ground."""
    unit.fallen = True
    queue_effect("@heavenly_light", unit, unit)


FAITH_TRANSFER_RATE = 0.2

# A Player unit whose faith is shaken all the way to 0 falls into Despair:
# it sits out its next DESPAIR_TURNS turns - no moving, no acting - under a
# dark cloud, then recovers with a little faith rekindled.
DESPAIR_TURNS = 3
DESPAIR_RECOVERY_FAITH = 30


def enter_despair_if_faithless(unit):
    """Puts a faithless Player unit into Despair. Returns whether it just
    fell into it (a unit already in Despair doesn't have its count reset)."""
    if unit.team != "Player" or unit.faith > 0 or unit.despair_turns > 0:
        return False
    unit.despair_turns = DESPAIR_TURNS
    return True


def begin_turn(unit, units_list=None):
    """Everything that happens as a unit's turn starts, before it (or its
    player) chooses anything. Returns what it may and may not do - `fled`
    means the unit left the battle and its turn is over."""
    unit.has_moved = False
    unit.has_acted = False
    if roll_flee(unit, units_list):
        return {"fled": True, "snared": False, "stunned": False, "despair_log": None,
                "lead_wore_off": False, "disarmed": False}
    end_morale_buff(unit)
    tick_buffs(unit)
    if unit.faith_ward_turns > 0:
        unit.faith_ward_turns -= 1
    apply_book_growth(unit, BOOK_REGISTRY)
    apply_morale_buff(unit)
    snared = unit.snared_turns > 0
    if snared:
        unit.snared_turns -= 1
        queue_effect("@snared", unit, unit)
    stunned = unit.stunned_turns > 0
    if stunned:
        unit.stunned_turns -= 1
        queue_effect("@stunned", unit, unit)
    unit.faith = max(0, unit.faith - unit.faith * 0.01)
    despair_log = tick_despair(unit)
    lead_wore_off = tick_lead(unit)
    disarmed = tick_disarm(unit)
    return {"fled": False, "snared": snared, "stunned": stunned, "despair_log": despair_log,
            "lead_wore_off": lead_wore_off, "disarmed": disarmed}


def tick_despair(unit):
    """Called at the start of a unit's turn. Returns None if the unit isn't
    in Despair; otherwise spends one of its Despair turns (the unit loses
    this turn) and returns the combat log line for it - recovering the unit
    when that was its last one."""
    if unit.despair_turns <= 0:
        return None
    unit.despair_turns -= 1
    if unit.despair_turns == 0:
        unit.faith = max(unit.faith, DESPAIR_RECOVERY_FAITH)
        unit.faith_popup = {"amount": round(unit.faith), "start": pygame.time.get_ticks()}
        queue_effect("@rekindle", unit, unit)
        return f"The cloud lifts from {unit.name} - their faith is rekindled!"
    queue_effect("@despair_turn", unit, unit)
    return f"{unit.name} is lost in despair and cannot act. ({unit.despair_turns} turns left)"


def preach_faith_change(preacher, target):
    """(signed faith change, whether it shakes faith) that Preach/Heal from
    `preacher` would cause `target` - before the 0..FAITH_CAP clamp. Shared
    by apply_preach and the battle preview so the two can't disagree."""
    # Magic Attack represents spiritual power/conviction, channeled here
    # into stronger Preaching and Healing (both route through this
    # function) rather than a separate damage stat, since this game has no
    # damage-number combat to plug it into.
    effective_faith = preacher.faith + preacher.magic_attack
    gain = effective_faith * FAITH_TRANSFER_RATE * CLASS_PREACH_MULTIPLIER.get(preacher.char_class, 1.0)
    # The enemy side preaching at the Player team is doubt and intimidation,
    # not the gospel: it wears the target's faith down instead of building
    # it up. Enemies tending their own allies (Heal) still restore faith.
    shakes_faith = preacher.team != "Player" and target.team == "Player"
    return (-gain if shakes_faith else gain), shakes_faith


# Whether a Faith attack (Preach aimed at the other side) reaches its
# target's heart depends on the preacher's Love - words spoken with
# compassion land; the same words without it fall on deaf ears. Heals on
# allies always land.
FAITH_BASE_HIT_CHANCE = 0.55
FAITH_HIT_PER_LOVE = 0.01
FAITH_MIN_HIT_CHANCE = 0.5
FAITH_MAX_HIT_CHANCE = 0.98


def faith_hit_chance(preacher):
    chance = FAITH_BASE_HIT_CHANCE + preacher.love * FAITH_HIT_PER_LOVE
    return max(FAITH_MIN_HIT_CHANCE, min(FAITH_MAX_HIT_CHANCE, chance))


def resolve_faith_attack(preacher, target, skill_name="Preach"):
    """A Faith-type skill (Preach) used on a target: rolls against
    faith_hit_chance, and on a hit applies it via apply_preach. Returns the
    combat log line."""
    if random.random() >= faith_hit_chance(preacher):
        report_action(skill_name, preacher, target, "miss")
        return f"{preacher.name} preaches to {target.name}, but the words fall on deaf ears. (Miss)"
    return apply_preach(preacher, target, skill_name)


def apply_preach(preacher, target, skill_name=None, gain=None, quiet=False):
    """Preach/Heal's faith change. skill_name, when given, is reported for
    particle effects along with how it turned out. Class skills pass their
    own `gain` (negative shakes faith); `quiet` plays the effects without a
    second EXP award, for the extra targets of an area skill."""
    if gain is None:
        gain, shakes_faith = preach_faith_change(preacher, target)
    else:
        shakes_faith = gain < 0
    report = (lambda *a, **k: queue_effect(*a, announce=False, **k)) if quiet else report_action
    if shakes_faith and target.faith_ward_turns > 0:
        report(skill_name, preacher, target, "blocked")
        return f"{target.name}'s shield of faith holds - their faith can't be shaken!"
    faith_before = target.faith
    target.faith = max(0, min(FAITH_CAP, target.faith + gain))
    actual_gain = target.faith - faith_before

    now = pygame.time.get_ticks()
    target.faith_popup = {"amount": round(actual_gain), "start": now + PREACH_BUBBLE_MS}

    if target.faith >= FAITH_CAP and target.team != "Player":
        convert_unit(target, "Player", now + PREACH_BUBBLE_MS)
        report(skill_name, preacher, target, "convert")
        return f"{target.name}'s faith is complete! They join the Player team - you command them now."
    if shakes_faith:
        if target.faith <= 0 and target.team != target.original_team:
            turn_back(target, now + PREACH_BUBBLE_MS)
            report(skill_name, preacher, target, "shaken")
            return f"{preacher.name} breaks {target.name}'s new faith - they turn back to the {target.team} side!"
        if enter_despair_if_faithless(target):
            report(skill_name, preacher, target, "despair")
            return f"{preacher.name} shatters {target.name}'s faith - a dark cloud of despair settles over them!"
        report(skill_name, preacher, target, "shaken")
        return f"{preacher.name} sows doubt in {target.name}, shaking their faith down to {round(target.faith)}!"
    report(skill_name, preacher, target, "hit")
    return f"{preacher.name} preaches to {target.name}, raising their faith to {round(target.faith)}!"


# --- Class signature skills ---
# Each of the sixteen classes (data/classes.csv, chosen by the new-game
# survey) carries one signature skill built from the game's own mechanics.
# Self-centred ones are cast on the caster's own tile and reach everyone
# within their radius. Each resolver does its own reporting (EXP, effects,
# banner) and leaves its combat log line in LAST_SIGNATURE_LOG.

SELF_CENTRED_SKILLS = {"Grand Design": 2, "Marshal": 2, "Inspire": 2, "Breaking Bread": 1, "Psalm": 2}
GRAND_DESIGN_BUFF = {"mv": 1, "speed": 5}
BUFF_TURNS = 2
MARSHAL_CT = 30
REASON_TOGETHER_FAITH = 25
DISPUTATION_FAITH = 10
INTERCESSION_FAITH = 30
PEACEMAKER_TURNS = 2
INSPIRE_FAITH = 15
GOOD_NEWS_SHARE = 0.6
PROVISION_FAITH = 10
SHIELD_OF_FAITH_TURNS = 2
ARREST_SNARE_TURNS = 3
BREAKING_BREAD_FAITH = 20
BREAKING_BREAD_LOVE = 10
PSALM_CT = 30
PSALM_FAITH = 10
BOLD_VENTURE_CHANCE = 0.55
BOLD_VENTURE_FAITH = 60
BOLD_VENTURE_BACKFIRE = 20
PARABLE_FAITH = 15
PARABLE_CT = 40
LAST_SIGNATURE_LOG = ""

# What the battle preview shows for each (besides any faith change).
SIGNATURE_PREVIEW = {
    "Grand Design": f"+{GRAND_DESIGN_BUFF['mv']} Move, +{GRAND_DESIGN_BUFF['speed']} Spd",
    "Reason Together": f"Faith +{REASON_TOGETHER_FAITH}",
    "Marshal": f"Allies CT +{MARSHAL_CT}",
    "Disputation": "Stun 1 turn",
    "Intercession": "Cure all + faith",
    "Peacemaker": f"Disarm {PEACEMAKER_TURNS} turns",
    "Inspire": f"Allies faith +{INSPIRE_FAITH}",
    "Good News": "Preach the crowd",
    "Provision": "MP full, freed",
    "Shield of Faith": "Guard + faith ward",
    "Arrest": f"Snare {ARREST_SNARE_TURNS} + disarm",
    "Breaking Bread": "Faith + Love",
    "Psalm": f"Enemies CT -{PSALM_CT}",
    "Bold Venture": f"{round(BOLD_VENTURE_CHANCE * 100)}%: faith +{BOLD_VENTURE_FAITH}",
    "Parable": f"Faith +{PARABLE_FAITH}, CT -{PARABLE_CT}",
}
# Sling is a Physical skill (a ranged disarm - see DISARM_SKILLS), so it
# resolves through resolve_physical_hit rather than resolve_signature.
SIGNATURE_SKILLS = set(SIGNATURE_PREVIEW)


def add_buff(unit, stats, turns=BUFF_TURNS):
    """Adds `stats` ({stat: amount}) now; they last through the unit's next
    `turns` turns (see tick_buffs)."""
    for stat, amount in stats.items():
        setattr(unit, stat, getattr(unit, stat) + amount)
    unit.buffs.append({"stats": dict(stats), "turns": turns})


def tick_buffs(unit):
    remaining = []
    for buff in unit.buffs:
        if buff["turns"] <= 0:
            for stat, amount in buff["stats"].items():
                setattr(unit, stat, getattr(unit, stat) - amount)
        else:
            buff["turns"] -= 1
            remaining.append(buff)
    unit.buffs = remaining


def within(center, units_list, radius, team, exclude=None):
    """Targetable units of `team` within `radius` tiles of `center`."""
    return [u for u in units_list if targetable(u) and u.team == team and u is not exclude
            and abs(u.x - center.x) + abs(u.y - center.y) <= radius]


def raise_faith(unit, amount):
    before = unit.faith
    unit.faith = min(FAITH_CAP, unit.faith + amount)
    if unit.faith != before:
        unit.faith_popup = {"amount": round(unit.faith - before), "start": pygame.time.get_ticks()}


def cure_statuses(unit):
    unit.stunned_turns = unit.snared_turns = unit.disarmed_turns = 0


def resolve_signature(skill_name, caster, target, units_list):
    """Resolves a class signature skill; always returns True (its log line,
    hit or miss, is left in LAST_SIGNATURE_LOG for skill_status_message)."""
    global LAST_SIGNATURE_LOG
    units_list = units_list or [caster, target]
    enemy_team = next((u.team for u in units_list if u.team != caster.team), "Enemy")

    def done(outcome, message, recipients=None):
        global LAST_SIGNATURE_LOG
        report_action(skill_name, caster, target, outcome, recipients)
        LAST_SIGNATURE_LOG = message
        return True

    def resisted():
        return random.random() < status_resist_chance(target)

    if skill_name == "Grand Design":
        allies = within(caster, units_list, SELF_CENTRED_SKILLS[skill_name], caster.team)
        for u in allies:
            add_buff(u, GRAND_DESIGN_BUFF)
        return done("hit", f"{caster.name} lays out a grand design - {len(allies)} allies move faster for {BUFF_TURNS} turns!", allies)
    if skill_name == "Marshal":
        allies = within(caster, units_list, SELF_CENTRED_SKILLS[skill_name], caster.team, exclude=caster)
        for u in allies:
            u.ct = min(100, u.ct + MARSHAL_CT)
        if not allies:
            return done("miss", f"{caster.name} calls the line to order, but no one is near enough to hear.")
        return done("hit", f"{caster.name} marshals the line - {len(allies)} allies surge forward!", allies)
    if skill_name == "Inspire":
        allies = within(caster, units_list, SELF_CENTRED_SKILLS[skill_name], caster.team)
        for u in allies:
            raise_faith(u, INSPIRE_FAITH)
        return done("hit", f"{caster.name} inspires the company - {len(allies)} hearts lift! (+{INSPIRE_FAITH} faith)", allies)
    if skill_name == "Breaking Bread":
        allies = within(caster, units_list, SELF_CENTRED_SKILLS[skill_name], caster.team)
        for u in allies:
            raise_faith(u, BREAKING_BREAD_FAITH)
            add_buff(u, {"love": BREAKING_BREAD_LOVE})
        return done("hit", f"{caster.name} breaks bread with {len(allies)} companions - faith and love grow!", allies)
    if skill_name == "Psalm":
        radius = SELF_CENTRED_SKILLS[skill_name]
        allies = within(caster, units_list, radius, caster.team)
        foes = within(caster, units_list, radius, enemy_team)
        for u in allies:
            raise_faith(u, PSALM_FAITH)
        for u in foes:
            u.ct = max(0, u.ct - PSALM_CT)
        return done("hit", f"{caster.name} sings a psalm - {len(foes)} foes fall still and {len(allies)} allies are refreshed.", allies + foes)
    if skill_name == "Reason Together":
        LAST_SIGNATURE_LOG = apply_preach(caster, target, skill_name, gain=REASON_TOGETHER_FAITH)
        return True
    if skill_name == "Disputation":
        if resisted():
            return done("miss", f"{target.name} keeps a cool head and won't be drawn into {caster.name}'s dispute.")
        target.stunned_turns = max(target.stunned_turns, 1)
        apply_preach(caster, target, skill_name, gain=DISPUTATION_FAITH, quiet=True)
        return done("hit", f"{caster.name} ties {target.name} in knots of argument - they're left reeling!")
    if skill_name == "Intercession":
        target.despair_turns = 0
        cure_statuses(target)
        raise_faith(target, INTERCESSION_FAITH)
        return done("hit", f"{caster.name} intercedes for {target.name} - every burden is lifted! (+{INTERCESSION_FAITH} faith)")
    if skill_name == "Peacemaker":
        if resisted():
            return done("miss", f"{target.name} won't lay down their arms - not yet.")
        target.disarmed_turns = max(target.disarmed_turns, PEACEMAKER_TURNS)
        return done("hit", f"{caster.name} makes peace with {target.name} - they lower their weapons for {PEACEMAKER_TURNS} turns!")
    if skill_name == "Good News":
        crowd = [target] + within(target, units_list, 1, target.team, exclude=target)
        chance = faith_hit_chance(caster)
        reached = 0
        for u in crowd:
            if random.random() < chance:
                gain = preach_faith_change(caster, u)[0] * GOOD_NEWS_SHARE
                apply_preach(caster, u, skill_name, gain=gain, quiet=u is not target)
                reached += 1
        if not reached:
            return done("miss", f"{caster.name} shares the good news, but the crowd isn't listening.")
        LAST_SIGNATURE_LOG = f"{caster.name} spreads the good news - {reached} of {len(crowd)} hear it gladly!"
        return True
    if skill_name == "Provision":
        target.mp = target.max_mp
        cure_statuses(target)
        raise_faith(target, PROVISION_FAITH)
        return done("hit", f"{caster.name} resupplies {target.name} - MP restored and ready to go!")
    if skill_name == "Shield of Faith":
        target.guarded = True
        target.faith_ward_turns = max(target.faith_ward_turns, SHIELD_OF_FAITH_TURNS)
        return done("hit", f"{caster.name} raises the shield of faith over {target.name} - guarded, and their faith can't be shaken!")
    if skill_name == "Arrest":
        if resisted():
            return done("miss", f"{target.name} slips {caster.name}'s grasp!")
        target.snared_turns = max(target.snared_turns, ARREST_SNARE_TURNS)
        target.disarmed_turns = max(target.disarmed_turns, 1)
        return done("hit", f"{caster.name} arrests {target.name} - bound for {ARREST_SNARE_TURNS} turns!")
    if skill_name == "Bold Venture":
        if random.random() < BOLD_VENTURE_CHANCE:
            LAST_SIGNATURE_LOG = "A bold venture pays off! " + apply_preach(caster, target, skill_name, gain=BOLD_VENTURE_FAITH)
            return True
        caster.faith = max(0, caster.faith - BOLD_VENTURE_BACKFIRE)
        caster.faith_popup = {"amount": -BOLD_VENTURE_BACKFIRE, "start": pygame.time.get_ticks()}
        enter_despair_if_faithless(caster)
        return done("miss", f"{caster.name}'s bold venture backfires - {target.name} scoffs, and {caster.name}'s faith is shaken. (-{BOLD_VENTURE_BACKFIRE})")
    if skill_name == "Parable":
        target.ct = max(0, target.ct - PARABLE_CT)
        LAST_SIGNATURE_LOG = f"{target.name} hangs on every word of the parable. " + apply_preach(caster, target, skill_name, gain=PARABLE_FAITH)
        return True
    LAST_SIGNATURE_LOG = f"{caster.name} uses {skill_name}."
    return True


ANKH_MIN_REVIVE_FAITH = 10


def apply_item_effect(item_name, user, target, units_list=None):
    """Resolve a consumable item's effect on its target. Returns a combat
    log message. Each item's potency is tied to the user's own stats, the
    same way Preach scales off the preacher's Faith."""
    item_data = ITEM_REGISTRY[item_name]
    effect = item_data["effect"]
    amount = item_data["amount"]
    now = pygame.time.get_ticks()
    report_action(item_name, user, target, "hit")
    user.speech_bubble_until = now + PREACH_BUBBLE_MS
    target.speech_bubble_until = now + PREACH_BUBBLE_MS

    if effect == "cure_status":
        target.stunned_turns = 0
        target.snared_turns = 0
        if target is user:
            return f"{user.name} tends their own wounds with a Healing Salve."
        return f"{user.name} applies a Healing Salve to {target.name}, easing their wounds!"

    if effect == "revive":
        target.removed = False
        target.removed_at = None
        # Love - compassion for others - adds straight onto the revived
        # Faith, on top of the fraction of the user's own Faith.
        target.faith = max(ANKH_MIN_REVIVE_FAITH, min(FAITH_CAP, round(user.faith * amount) + user.love))
        target.faith_popup = {"amount": round(target.faith), "start": now + PREACH_BUBBLE_MS}
        return f"{user.name} touches {target.name} with an Ankh - breath returns to them!"

    if effect == "restore_mp":
        target.mp = target.max_mp
        if target is user:
            return f"{user.name} draws on the Myrrh's fragrance, restoring their own strength."
        return f"{user.name} shares Myrrh with {target.name}, restoring their strength!"

    if effect == "buff_magic_attack":
        gain = round(user.magic_attack * amount)
        target.magic_attack += gain
        return f"{user.name} offers Frankincense to {target.name}, sharpening their spirit! (+{gain} Speech)"

    if effect == "faith_boost":
        faith_before = target.faith
        # Love adds its own weight to a Mustard Seed's blessing on someone
        # else, same idea as the Ankh revive bonus above.
        love_bonus = user.love if target is not user else 0
        target.faith = max(0, min(FAITH_CAP, target.faith + amount + love_bonus))
        actual_gain = target.faith - faith_before
        target.faith_popup = {"amount": round(actual_gain), "start": now + PREACH_BUBBLE_MS}
        return f"{user.name} plants a Mustard Seed of faith in {target.name} - it grows to {round(target.faith)}!"

    return f"{user.name} uses {item_name} on {target.name}."


def draw_dialogue_window(surface, speaker, text, frame=None):
    # Dialogue gets its own larger fonts than the general HUD so story text is
    # comfortable to read; line spacing follows the font's own line height.
    speaker_font = get_font(40, bold=True)
    font = get_font(36)
    hint_font = get_font(24)
    width, height = 1200, 340
    window = pygame.Rect(SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT - height - 40, width, height)
    if frame:
        draw_nine_slice_panel(surface, window, frame)
        content = frame_content_rect(window, frame)
    else:
        pygame.draw.rect(surface, (15, 15, 25), window)
        pygame.draw.rect(surface, CURSOR_COLOR, window, 2)
        content = pygame.Rect(window.x + 18, window.y + 14, window.width - 36, window.height - 28)

    surface.blit(speaker_font.render(speaker, True, CURSOR_COLOR), (content.x, content.y))
    text_top = content.y + speaker_font.get_linesize() + 8

    words = text.split()
    lines = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if font.size(candidate)[0] <= content.width:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    for line_index, line in enumerate(lines):
        surface.blit(font.render(line, True, (240, 240, 240)), (content.x, text_top + line_index * font.get_linesize()))
    hint = hint_font.render("[Space / Enter] Continue", True, (160, 160, 160))
    surface.blit(hint, (content.right - hint.get_width(), content.bottom - hint.get_height()))


def action_menu_layout(current_menu, frame=None):
    """Shared by draw_action_menu and the mouse-click hit-test below it in
    main() - both need the exact same panel/content geometry, or clicks
    stop lining up with what's actually drawn."""
    width = 300
    # The box grows/shrinks with however many rows current_menu has (the
    # root menu has 4 entries; skill/item submenus vary in length) - no
    # portrait is shown here, so there's nothing else to reserve space for.
    box_height = 110 + len(current_menu) * 26
    mx, my = SCREEN_WIDTH - width - 20, 30
    panel_rect = pygame.Rect(mx, my, width, box_height)
    if frame:
        content = frame_content_rect(panel_rect, frame)
    else:
        content = pygame.Rect(mx + 10, my + 10, width - 20, box_height - 20)
    return panel_rect, content


def draw_action_menu(surface, font, active_unit, current_menu, menu_index, units, team_inventory=None, frame=None):
    if not active_unit:
        return
    panel_rect, content = action_menu_layout(current_menu, frame)
    if frame:
        draw_nine_slice_panel(surface, panel_rect, frame)
    else:
        pygame.draw.rect(surface, (20, 20, 30), panel_rect)
        pygame.draw.rect(surface, CURSOR_COLOR, panel_rect, 2)

    surface.blit(font.render(f"{active_unit.name} Actions", True, (255, 255, 255)), (content.x, content.y))
    for idx, opt in enumerate(current_menu):
        no_items_left = not any((team_inventory or {}).get(active_unit.team, {}).values())
        if ((opt == "Move" and (active_unit.has_moved or not can_unit_move(active_unit, units)))
                or (opt == "Act" and active_unit.has_acted)
                or (opt == "Item" and (active_unit.has_acted or no_items_left))):
            opt_color = (70, 70, 70)
        else:
            opt_color = CURSOR_COLOR if idx == menu_index else (170, 170, 170)
        pointer = " -> " if idx == menu_index else "    "
        surface.blit(font.render(f"{pointer}{opt}", True, opt_color), (content.x, content.y + 35 + (idx * 26)))


def draw_unit_profile(surface, font, unit, portraits, bottom_right):
    if not unit:
        return
    # Portrait is 2.5x the old 84x42 thumbnail; name/class/bars move to its
    # right instead of stacking below, so the box grows wider, not taller.
    margin = 10
    portrait_w, portrait_h = 210, 105
    stats_w = 200
    width = margin + portrait_w + margin + stats_w + margin
    height = portrait_h + margin * 2
    right, bottom = bottom_right
    px, py = right - width, bottom - height

    pygame.draw.rect(surface, (20, 20, 30), (px, py, width, height))
    pygame.draw.rect(surface, CURSOR_COLOR, (px, py, width, height), 2)

    portrait = portraits.get(unit.name)
    if portrait:
        thumb = pygame.transform.smoothscale(portrait, (portrait_w, portrait_h))
        surface.blit(thumb, (px + margin, py + margin))

    stats_x = px + margin + portrait_w + margin
    name_color = (100, 180, 255) if unit.team == "Player" else (255, 110, 110)
    surface.blit(font.render(unit.name, True, name_color), (stats_x, py + 18))
    class_label = f"Lv {unit.level}  {unit.char_class}" if unit.char_class else f"Lv {unit.level}"
    if unit.mount:
        class_label += "  (Mounted)"
    surface.blit(font.render(class_label, True, (180, 180, 180)), (stats_x, py + 38))

    bar_x, bar_w, bar_h = stats_x, stats_w, 16

    faith_y = py + 62
    faith_pct = max(0, min(1, unit.faith / FAITH_CAP))
    pygame.draw.rect(surface, (60, 50, 10), (bar_x, faith_y, bar_w, bar_h))
    pygame.draw.rect(surface, (255, 215, 0), (bar_x, faith_y, int(bar_w * faith_pct), bar_h))
    pygame.draw.rect(surface, (230, 230, 230), (bar_x, faith_y, bar_w, bar_h), 1)
    faith_text = font.render(f"FAITH {round(unit.faith)}/{FAITH_CAP}", True, (255, 255, 255))
    surface.blit(faith_text, faith_text.get_rect(center=(bar_x + bar_w // 2, faith_y + bar_h // 2)))

    mp_y = faith_y + bar_h + 8
    mp_pct = max(0, unit.mp / unit.max_mp) if unit.max_mp else 0
    pygame.draw.rect(surface, (20, 20, 60), (bar_x, mp_y, bar_w, bar_h))
    pygame.draw.rect(surface, (70, 140, 230), (bar_x, mp_y, int(bar_w * mp_pct), bar_h))
    pygame.draw.rect(surface, (230, 230, 230), (bar_x, mp_y, bar_w, bar_h), 1)
    mp_text = font.render(f"MP {unit.mp}/{unit.max_mp}", True, (255, 255, 255))
    surface.blit(mp_text, mp_text.get_rect(center=(bar_x + bar_w // 2, mp_y + bar_h // 2)))

    # EXP toward the next level: a thin bar with its count beside it.
    exp_y = mp_y + bar_h + 6
    exp_w = bar_w - 70
    pygame.draw.rect(surface, (20, 30, 45), (bar_x, exp_y, exp_w, 6))
    pygame.draw.rect(surface, (140, 210, 255), (bar_x, exp_y, int(exp_w * unit.exp / EXP_PER_LEVEL), 6))
    exp_text = font.render(f"EXP {unit.exp}", True, (140, 210, 255))
    surface.blit(exp_text, exp_text.get_rect(midleft=(bar_x + exp_w + 8, exp_y + 3)))


def predict_action(attacker, target, skill_name, units_list=None):
    """What using `skill_name` on `target` would do, for the battle preview
    (Final Fantasy Tactics' pre-attack readout): the chance it lands, the
    target's faith before/after, and a short outcome label. Mirrors the
    real resolution functions without changing any unit."""
    skill = SKILL_REGISTRY[skill_name]
    kind = skill["type"]
    faith_after = target.faith
    if kind in ("Faith", "Heal"):
        change, shakes_faith = preach_faith_change(attacker, target)
        faith_after = max(0, min(FAITH_CAP, target.faith + change))
        if shakes_faith:
            outcome = "DESPAIR" if faith_after <= 0 and target.despair_turns == 0 else "Faith shaken"
        elif faith_after >= FAITH_CAP and target.team != "Player":
            outcome = "CONVERT!"
        else:
            outcome = "Faith up"
        chance = faith_hit_chance(attacker) if kind == "Faith" else 1.0
    elif kind == "Physical":
        if target.guarded:
            chance, outcome = 0.0, "Guard blocks it"
        elif skill_name in DISARM_SKILLS:
            chance = physical_hit_chance(attacker, target, units_list)
            outcome = f"Disarm {DISARM_TURNS} turns"
        else:
            chance, outcome = physical_hit_chance(attacker, target, units_list), "KO"
    elif skill_name == "Shove":
        chance = SHOVE_CHANCE * (1 - status_resist_chance(target))
        outcome = f"Stun + push {CLASS_SHOVE_DISTANCE.get(attacker.char_class, SHOVE_DISTANCE)}"
    elif skill_name == "Fish net":
        chance, outcome = 1 - status_resist_chance(target), "Snare 2 turns"
    elif skill_name == "Defend":
        chance, outcome = 1.0, "Guard"
    elif skill_name == "Rally":
        excess, _ = rally_need(target)
        faith_after = target.faith + (excess if target.team == "Player" else -excess)
        chance, outcome = 1.0, "Rally"
    elif skill_name == "Command":
        chance, outcome = 1.0, f"CT +{COMMAND_CT_BOOST}"
    elif skill_name == "Lead":
        count = len(lead_recipients(attacker, units_list or [attacker]))
        chance, outcome = 1.0, f"Love +{LEAD_LOVE_BONUS} x{count}"
    elif skill_name in SIGNATURE_SKILLS:
        chance, outcome = 1.0, SIGNATURE_PREVIEW[skill_name]
        faith_shift = {"Reason Together": REASON_TOGETHER_FAITH, "Parable": PARABLE_FAITH, "Disputation": DISPUTATION_FAITH,
                       "Intercession": INTERCESSION_FAITH, "Provision": PROVISION_FAITH, "Bold Venture": BOLD_VENTURE_FAITH}
        if skill_name in faith_shift:
            faith_after = min(FAITH_CAP, target.faith + faith_shift[skill_name])
        if skill_name in ("Disputation", "Peacemaker", "Arrest"):
            chance = 1 - status_resist_chance(target)
        elif skill_name == "Good News":
            chance = faith_hit_chance(attacker)
        elif skill_name == "Bold Venture":
            chance = BOLD_VENTURE_CHANCE
    else:
        chance, outcome = 1.0, skill_name
    return {"chance": chance, "faith_before": target.faith, "faith_after": faith_after, "outcome": outcome}


PREVIEW_CARD_W, PREVIEW_CENTER_W, PREVIEW_H = 360, 230, 132


def draw_preview_card(surface, font, unit, portraits, rect, faith_after=None, mirrored=False):
    """One side of the battle preview: portrait, name, class, and faith/MP
    bars. With faith_after, the faith bar blinks the predicted change -
    the part gained in pale gold, the part lost in red."""
    pygame.draw.rect(surface, (20, 20, 30), rect)
    pygame.draw.rect(surface, (100, 180, 255) if unit.team == "Player" else (255, 110, 110), rect, 2)
    margin = 10
    portrait_w, portrait_h = 140, 70
    portrait_x = rect.right - margin - portrait_w if mirrored else rect.x + margin
    portrait = portraits.get(unit.name)
    if portrait:
        surface.blit(pygame.transform.smoothscale(portrait, (portrait_w, portrait_h)), (portrait_x, rect.y + margin))
    text_x = rect.x + margin if mirrored else rect.x + margin + portrait_w + margin
    name_color = (100, 180, 255) if unit.team == "Player" else (255, 110, 110)
    surface.blit(font.render(unit.name, True, name_color), (text_x, rect.y + 14))
    class_label = f"Lv {unit.level}  {unit.char_class}" if unit.char_class else f"Lv {unit.level}"
    if unit.mount:
        class_label += "  (Mounted)"
    surface.blit(font.render(class_label, True, (180, 180, 180)), (text_x, rect.y + 36))

    bar_x, bar_y, bar_w, bar_h = rect.x + margin, rect.y + margin + portrait_h + 10, rect.width - margin * 2, 16
    before = max(0.0, min(1.0, unit.faith / FAITH_CAP))
    pygame.draw.rect(surface, (60, 50, 10), (bar_x, bar_y, bar_w, bar_h))
    blink_on = (pygame.time.get_ticks() // 350) % 2 == 0
    if faith_after is None or round(faith_after) == round(unit.faith):
        pygame.draw.rect(surface, (255, 215, 0), (bar_x, bar_y, int(bar_w * before), bar_h))
        label = f"FAITH {round(unit.faith)}/{FAITH_CAP}"
    else:
        after = max(0.0, min(1.0, faith_after / FAITH_CAP))
        low, high = min(before, after), max(before, after)
        pygame.draw.rect(surface, (255, 215, 0), (bar_x, bar_y, int(bar_w * low), bar_h))
        change_color = (255, 245, 170) if faith_after > unit.faith else (230, 60, 60)
        if blink_on:
            pygame.draw.rect(surface, change_color, (bar_x + int(bar_w * low), bar_y, int(bar_w * (high - low)) or 1, bar_h))
        label = f"FAITH {round(unit.faith)} > {round(faith_after)}"
    pygame.draw.rect(surface, (230, 230, 230), (bar_x, bar_y, bar_w, bar_h), 1)
    # Dark outline so the numbers read over the gold bar.
    center = (bar_x + bar_w // 2, bar_y + bar_h // 2)
    shadow = font.render(label, True, (10, 10, 10))
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        surface.blit(shadow, shadow.get_rect(center=(center[0] + dx, center[1] + dy)))
    text = font.render(label, True, (255, 255, 255))
    surface.blit(text, text.get_rect(center=center))


def draw_battle_preview(surface, font, attacker, target, skill_name, units, portraits, bottom_center):
    """The pre-attack readout shown while aiming an Act at a unit: the
    attacker's card, the skill with its hit chance and predicted outcome,
    and the target's card with its faith change previewed."""
    prediction = predict_action(attacker, target, skill_name, units)
    total_w = PREVIEW_CARD_W * 2 + PREVIEW_CENTER_W
    left = bottom_center[0] - total_w // 2
    top = bottom_center[1] - PREVIEW_H
    attacker_rect = pygame.Rect(left, top, PREVIEW_CARD_W, PREVIEW_H)
    center_rect = pygame.Rect(left + PREVIEW_CARD_W, top, PREVIEW_CENTER_W, PREVIEW_H)
    target_rect = pygame.Rect(center_rect.right, top, PREVIEW_CARD_W, PREVIEW_H)

    draw_preview_card(surface, font, attacker, portraits, attacker_rect)
    faith_after = prediction["faith_after"] if prediction["faith_after"] != prediction["faith_before"] else None
    draw_preview_card(surface, font, target, portraits, target_rect, faith_after=faith_after, mirrored=True)

    pygame.draw.rect(surface, (12, 12, 20), center_rect)
    pygame.draw.rect(surface, CURSOR_COLOR, center_rect, 2)
    skill_color = SKILL_REGISTRY[skill_name].get("color", (255, 255, 255))
    name = font.render(skill_name, True, skill_color)
    surface.blit(name, name.get_rect(center=(center_rect.centerx, center_rect.y + 20)))

    chance = round(prediction["chance"] * 100)
    chance_color = (120, 255, 140) if chance >= 80 else (255, 215, 0) if chance >= 50 else (255, 110, 110)
    big = get_font(56).render(f"{chance}%", True, chance_color)
    surface.blit(big, big.get_rect(center=(center_rect.centerx, center_rect.y + 60)))

    outcome = font.render(prediction["outcome"], True, (240, 240, 240))
    surface.blit(outcome, outcome.get_rect(center=(center_rect.centerx, center_rect.y + 98)))
    arrow_y = center_rect.bottom - 14
    pygame.draw.polygon(surface, CURSOR_COLOR, [(center_rect.centerx + 16, arrow_y), (center_rect.centerx - 6, arrow_y - 7), (center_rect.centerx - 6, arrow_y + 7)])


def targetable(unit):
    """Whether a unit can be the target of anything - Acts, items or AI
    attention. `disabled` units (none by default - converts now fight for
    their new side) are off limits to both sides."""
    return unit.is_alive() and not unit.disabled


def find_unit_at_tile(units, x, y):
    return next((u for u in units if u.is_alive() and u.x == x and u.y == y), None)


# Paul leads the mission: if his faith is ever broken to 0 the battle is
# lost on the spot, whoever else is still standing.
LEADER_NAME = "Paul"


def leader_faith_broken(units):
    return any(u.name == LEADER_NAME and u.original_team == "Player" and u.faith <= 0 for u in units)


def get_winner(units):
    if leader_faith_broken(units):
        return "Enemy"
    alive_teams = {u.team for u in units if u.is_alive()}
    if len(alive_teams) == 1:
        return next(iter(alive_teams))
    return None


AI_ACTION_DELAY_MS = 500


def is_ai_team(team):
    return str(team).lower() in {"enemy", "blue"}


def shove_cluster_size(target, units_list):
    """How many of the target's own side stand right next to it - Shove is
    worth using when two or more of them are bunched together."""
    return sum(
        1 for u in units_list
        if u is not target and targetable(u) and u.team == target.team
        and abs(u.x - target.x) + abs(u.y - target.y) == 1
    )


def score_ai_candidate(unit, skill_name, skill_data, target, distance, units_list):
    """How much the AI wants to use this skill on this target (higher is
    better), or None if it shouldn't. Scores sit in rough bands so the kind
    of action matters more than small differences between targets:
    Shove on a cluster > Shoot > Preach > Slash > heals > status > support."""
    kind = skill_data["type"]
    if kind == "Heal":
        if target is unit or target.faith >= FAITH_CAP:
            return None
        return 40 + 30 * (1 - target.faith / FAITH_CAP)
    if kind == "Support":
        if skill_name == "Defend":
            return None if target.guarded else 20
        if skill_name == "Command":
            return None if target is unit else 22
        if skill_name == "Lead":
            recipients = len(lead_recipients(unit, units_list))
            return 30 if recipients >= 2 else None
        if skill_name == "Rally":
            # Worth more the closer the ally was to being converted; freeing
            # a stunned/snared/disarmed ally is worth doing on its own.
            excess, statused = rally_need(target)
            if target is unit or not (excess or statused):
                return None
            return 40 + 40 * excess / RALLY_FAITH_RESTORE + (20 if statused else 0)
        return 15
    if skill_name == "Shove":
        # Only worth it into a crowd: 2+ characters standing together.
        cluster = shove_cluster_size(target, units_list)
        return 70 + 2 * cluster if cluster >= 1 else None
    if kind == "Status":
        if skill_name == "Fish net":
            # A net is for catching someone at range, not a lock: never on a
            # target already snared, only on one 2+ tiles away, and never two
            # turns running - so net-throwers still close in and engage.
            if target.snared_turns > 0 or distance < 2 or unit.ai_netted_last_turn:
                return None
        return 30
    if kind == "Faith":
        _, shakes_faith = preach_faith_change(unit, target)
        closeness = target.faith / FAITH_CAP
        # Sowing doubt goes after the weakest believer, to break them into
        # despair; preaching the gospel goes after whoever is closest to
        # conversion.
        return 50 + 20 * ((1 - closeness) if shakes_faith else closeness)
    if kind == "Physical":
        if skill_name in DISARM_SKILLS:
            return None if target.disarmed_turns > 0 else 45 + 10 * target.faith / FAITH_CAP
        return 55
    return 10


def choose_ai_action(unit, units_list):
    if unit.has_acted:
        # Disarmed this turn: it can only move.
        return {"action": "skip", "reason": "Can't act this turn."}
    allies = [u for u in units_list if targetable(u) and u.team == unit.team]
    enemies = [u for u in units_list if targetable(u) and u.team != unit.team]
    if not enemies and not allies:
        return {"action": "skip", "reason": "No units remain."}

    best_choice = None
    for skill_name in unit.skills:
        skill_data = SKILL_REGISTRY.get(skill_name)
        if not skill_data or unit.mp < skill_data["mp_cost"]:
            continue
        friendly = skill_data["type"] in ("Heal", "Support")
        for target in (allies if friendly else enemies):
            distance = abs(unit.x - target.x) + abs(unit.y - target.y)
            if distance > skill_data["range"]:
                continue
            if distance == 0 and not friendly:
                continue
            score = score_ai_candidate(unit, skill_name, skill_data, target, distance, units_list)
            if score is None:
                continue
            candidate = {"action": "skill", "skill": skill_name, "target": target, "priority": (-score, distance)}
            if best_choice is None or candidate["priority"] < best_choice["priority"]:
                best_choice = candidate

    unit.ai_netted_last_turn = best_choice is not None and best_choice["skill"] == "Fish net"
    if best_choice is not None:
        return best_choice

    if not enemies:
        return {"action": "skip", "reason": "No enemies remain."}
    return {"action": "skip", "reason": "No valid attack or spell in range."}


def get_ai_move_destination(unit, units_list):
    allies = [u for u in units_list if targetable(u) and u.team == unit.team]
    injured_allies = [u for u in allies if u.faith < FAITH_CAP and u != unit]
    enemies = [u for u in units_list if targetable(u) and u.team != unit.team]
    rally_allies = [u for u in allies if u != unit and any(rally_need(u))] if "Rally" in unit.skills else []
    if rally_allies:
        # Medics make for whichever ally is nearest to being converted.
        target = max(rally_allies, key=lambda u: (u.faith, -(abs(unit.x - u.x) + abs(unit.y - u.y))))
    elif injured_allies and any(skill_name for skill_name in unit.skills if SKILL_REGISTRY.get(skill_name, {}).get("type") == "Heal"):
        target = min(injured_allies, key=lambda u: (u.faith, abs(unit.x - u.x) + abs(unit.y - u.y)))
    elif enemies:
        target = min(enemies, key=lambda u: (abs(unit.x - u.x) + abs(unit.y - u.y), -u.faith))
    else:
        return None

    best_step = None
    best_score = None

    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nx, ny = unit.x + dx, unit.y + dy
        if not (0 <= nx < MAP_COLS and 0 <= ny < MAP_ROWS):
            continue
        if any(u.is_alive() and u.x == nx and u.y == ny and u != unit for u in units_list):
            continue
        if (nx, ny) in PROP_TILES:
            continue
        score = (abs(nx - target.x) + abs(ny - target.y), -(nx + ny))
        if best_score is None or score < best_score:
            best_score = score
            best_step = (nx, ny)

    if best_step is not None:
        return best_step

    return None


def rotate_grid_position(x, y, rotation, map_cols, map_rows):
    if rotation == 1:
        return y, map_rows - 1 - x
    if rotation == 2:
        return map_cols - 1 - x, map_rows - 1 - y
    if rotation == 3:
        return map_cols - 1 - y, x
    return x, y


def get_render_order(map_cols, map_rows, rotation):
    cells = []
    for y in range(map_rows):
        for x in range(map_cols):
            rx, ry = rotate_grid_position(x, y, rotation, map_cols, map_rows)
            cells.append((rx + ry, ry, rx, x, y))
    cells.sort()
    return [(x, y) for _, _, _, x, y in cells]


def iso_to_screen(map_x, map_y, map_z, origin_x, origin_y, rotation=0, map_cols=0, map_rows=0, zoom=1.0):
    rx, ry = rotate_grid_position(map_x, map_y, rotation, map_cols, map_rows)
    screen_x = origin_x + (rx - ry) * (TILE_WIDTH * zoom / 2)
    screen_y = origin_y + (rx + ry) * (TILE_HEIGHT * zoom / 2) - (map_z * TILE_RISE * zoom)
    return screen_x, screen_y


# Every tile draws with at least this much visible side-wall "thickness,"
# even at height 0, so the map reads as a grid of resting cubes/blocks
# rather than flat painted diamonds. Elevation adds on top of this base.
TILE_DEPTH_BASE = 16

# Brightness multiplier for a slope's texture, by which way its face turns.
# A face turned toward the camera sits partway between a lit top and its
# matching wall (draw_iso_tile's +rx-facing right wall is 0.7, its
# +ry-facing left wall 0.5). A face turned away is seen at a grazing angle
# and is shaded slightly too - brightening it instead made it read as a
# pale flat tile rather than a ramp.
SLOPE_SHADE_TOWARD_RX = 0.85
SLOPE_SHADE_TOWARD_RY = 0.75
SLOPE_SHADE_AWAY = 0.9

_slope_texture_cache = {}


def build_slope_texture(terrain_image, tile_width, tile_height, rise, corner_offsets):
    """Shears a terrain sprite's top face (see assets.terrain_top_face) onto
    a slope's tilted top face - the sprite's baked slab edges are left off,
    since draw_iso_tile's own walls already taper to follow the slope.
    A planar slope is an affine warp of the flat diamond, and one that only
    ever moves pixels vertically - so it's done a pixel column at a time:
    each column is scaled vertically by the same factor and shifted by an
    amount that varies linearly across the tile. The returned surface is
    `rise` taller than the flat tile, with the flat tile's top at rise / 2
    (a slope's corners move at most half a height step either way)."""
    top, right, _, left = corner_offsets
    # The top face's height offset is top + climb_u * u + climb_v * v, where
    # u runs top->right corner and v runs top->left corner across the tile.
    climb_u, climb_v = right - top, left - top
    column_height = max(1, round(tile_height - (climb_u + climb_v) * rise))

    flat = pygame.transform.smoothscale(terrain_top_face(terrain_image), (tile_width, tile_height))
    sloped = pygame.Surface((tile_width, tile_height + math.ceil(rise)), pygame.SRCALPHA)
    for column_x in range(tile_width):
        column = pygame.transform.smoothscale(flat.subsurface((column_x, 0, 1, tile_height)), (1, column_height))
        across = (column_x + 0.5) / tile_width - 0.5
        shift = rise / 2 - top * rise - (climb_u - climb_v) * rise * across
        sloped.blit(column, (column_x, round(shift)))

    # A lower right/left corner than the top corner means the face turns
    # toward the camera along that axis.
    if climb_u < 0:
        shade = SLOPE_SHADE_TOWARD_RX
    elif climb_v < 0:
        shade = SLOPE_SHADE_TOWARD_RY
    else:
        shade = SLOPE_SHADE_AWAY
    level = round(255 * shade)
    sloped.fill((level, level, level, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return sloped


# --- Map lighting ---
# Each tile gets a light level (1.0 = as drawn) worked out once per map in
# world space, so it turns with the map when the view rotates. The sun
# shines from SUN_DIRECTION (in grid steps) - the upper left of the screen
# in the battle's opening view (rotation 2) - so tiles fall off gently
# away from it, high ground catches more light, anything taller
# between a tile and the sun - a higher neighbor, a tree, a boulder -
# shades it, and a few soft sun-patches and cloud-shadows break it up.
LIGHT_FALLOFF = 0.2           # how much darker the far corner is than the sun's
LIGHT_PER_HEIGHT = 0.035      # extra light per unit of height
LIGHT_MIN, LIGHT_MAX = 0.55, 1.15
SUN_DIRECTION = (1.0, 0.4)
# Neighbors on the sun's side that can shade a tile, and how strongly.
SUNWARD_NEIGHBORS = ((1, 0, 1.0), (0, 1, 0.45), (1, 1, 0.5))
TERRAIN_SHADOW_PER_HEIGHT = 0.12
TERRAIN_SHADOW_MAX = 0.28
PROP_SHADOW = {"tree": 0.16, "boulder": 0.1}
# Colors a dim / bright tile is tinted toward - shadows go cool, sunlight
# goes warm, the way painted backgrounds usually light a scene.
SHADOW_TINT = (12, 16, 42)
SUNLIGHT_TINT = (255, 226, 160)


def compute_tile_lighting(map_data, props_by_tile=None):
    """{(x, y): light level} for every tile. Deterministic per map layout,
    so a stage always looks the same."""
    rows = len(map_data)
    cols = len(map_data[0]) if rows else 0
    props_by_tile = props_by_tile or {}
    rng = random.Random(repr(map_data))
    patches = []
    for _ in range(max(2, (rows * cols) // 20)):
        patches.append((rng.uniform(0, cols - 1), rng.uniform(0, rows - 1),
                        rng.uniform(1.5, 3.0), rng.choice((0.12, -0.16, -0.12))))
    sun_x, sun_y = SUN_DIRECTION
    span = max(1e-6, (cols - 1) * sun_x + (rows - 1) * sun_y)

    def height_at(x, y):
        if 0 <= y < rows and 0 <= x < cols:
            return map_data[y][x]
        return None

    lighting = {}
    for y in range(rows):
        for x in range(cols):
            z = map_data[y][x]
            toward_sun = (x * sun_x + y * sun_y) / span  # 1 at the sunniest corner
            light = 1.05 - LIGHT_FALLOFF * (1 - toward_sun)
            light += LIGHT_PER_HEIGHT * z
            for dx, dy, weight in SUNWARD_NEIGHBORS:
                neighbor_z = height_at(x + dx, y + dy)
                if neighbor_z is not None and neighbor_z - z >= 0.5:
                    light -= min(TERRAIN_SHADOW_MAX, TERRAIN_SHADOW_PER_HEIGHT * (neighbor_z - z)) * weight
                prop = props_by_tile.get((x + dx, y + dy))
                if prop:
                    light -= PROP_SHADOW.get(prop["prop"], 0.1) * weight
            for px, py, radius, amount in patches:
                light += amount * max(0.0, 1 - math.hypot(x - px, y - py) / radius)
            lighting[(x, y)] = max(LIGHT_MIN, min(LIGHT_MAX, light))
    return lighting


def light_tint(light):
    """The RGBA overlay that brings a tile drawn at full brightness to the
    given light level, or None when it's close enough to 1 to skip."""
    if light < 0.98:
        return (*SHADOW_TINT, round(min(1.0, (1 - light) * 1.25) * 255))
    if light > 1.02:
        return (*SUNLIGHT_TINT, round((light - 1) * 0.9 * 255))
    return None


def draw_iso_tile(surface, sx, sy, height, color, terrain_image=None, zoom=1.0, wall_color=None, corner_offsets=FLAT_CORNER_OFFSETS, light=1.0):
    """Draws one tile block. corner_offsets (see controls.tile_corner_offsets)
    tilts its top face into a slope; its walls still reach down to the same
    ground line, so they taper to follow the slope. `light` (see
    compute_tile_lighting) tints the whole block darker or brighter."""
    tile_width = TILE_WIDTH * zoom
    tile_height = TILE_HEIGHT * zoom
    rise = TILE_RISE * zoom
    h_offset = (height * TILE_RISE + TILE_DEPTH_BASE) * zoom
    top_points = tile_top_points(sx, sy, zoom, corner_offsets)
    ground_points = [(px, py + offset * rise + h_offset) for (px, py), offset in zip(top_points, corner_offsets)]
    wall_base = wall_color if wall_color is not None else color
    left_wall = [top_points[3], top_points[2], ground_points[2], ground_points[3]]
    pygame.draw.polygon(surface, (int(wall_base[0]*0.5), int(wall_base[1]*0.5), int(wall_base[2]*0.5)), left_wall)
    right_wall = [top_points[2], top_points[1], ground_points[1], ground_points[2]]
    pygame.draw.polygon(surface, (int(wall_base[0]*0.7), int(wall_base[1]*0.7), int(wall_base[2]*0.7)), right_wall)

    if terrain_image and corner_offsets != FLAT_CORNER_OFFSETS:
        size = (round(tile_width), round(tile_height))
        cache_key = (id(terrain_image), size, round(rise, 3), tuple(corner_offsets))
        image = _slope_texture_cache.get(cache_key)
        if image is None:
            image = build_slope_texture(terrain_image, size[0], size[1], rise, corner_offsets)
            _slope_texture_cache[cache_key] = image
        surface.blit(image, (round(sx - tile_width / 2), round(sy - rise / 2)))
    elif terrain_image:
        image = pygame.transform.smoothscale(terrain_image, (round(tile_width), round(tile_height)))
        surface.blit(image, (round(sx - tile_width / 2), round(sy)))
    else:
        pygame.draw.polygon(surface, color, top_points)
        draw_tile_texture(surface, top_points, height, color)

    tint = light_tint(light)
    if tint:
        # The block's whole silhouette - top face plus both walls - so the
        # tile darkens or brightens as one piece.
        silhouette = [top_points[0], top_points[1], ground_points[1], ground_points[2], ground_points[3], top_points[3]]
        pygame.gfxdraw.filled_polygon(surface, [(round(px), round(py)) for px, py in silhouette], tint)

    return top_points


# Target-range highlight while aiming an Act or item: the fill (its alpha
# pulses between 90 and 140) and the tile outline.
TARGET_RANGE_COLOR = (230, 40, 40)
TARGET_RANGE_EDGE = (255, 110, 110)


UNIT_CELL_FILL = 0.8
# A unit's visual "slot" is larger than the flat tile footprint (TILE_WIDTH x
# TILE_HEIGHT) since standee sprites are meant to rise above/overlap the tile
# they stand on. This matches the sprite footprint used before per-zoom sizing
# was added (140x70 at zoom 1).
UNIT_SLOT_WIDTH = 140
UNIT_SLOT_HEIGHT = 70
# On-map unit art size, as a multiplier on top of the slot size above.
# Set above 1.0 to make unit art bigger/more readable on a sparse map -
# reverted to 1.0 (the original size) since 2.5x overlapped badly once units
# clustered together on a crowded battlefield.
UNIT_ART_SCALE = 1.0
# Which art the on-map token uses: "icons" (each character's own original
# small sprite - the current choice), "pixel" (small FFT-style chibi
# pixel-art sprites by job class, tried and reverted) or "chess" (classic
# chess pieces, tried and reverted - too literal).
UNIT_ART_STYLE = "icons"

# Mounts, by the `mount` column in characters.csv: the Move tiles riding
# adds, and the art drawn over the lower part of the rider's token (legs
# and stand) so the rider sits in the saddle - its width as a fraction of
# the unit's cell, and where the saddle's centre sits, as fractions of the
# art's size and of the cell height below the token's centre.
MOUNTS = {
    "horse": {"mv": 3, "art": "assets/horse.png", "width": 0.62, "saddle": (0.53, 0.47), "seat_y": 0.12},
}
_mount_art_cache = {}


def mount_art(mount):
    if mount not in _mount_art_cache:
        path = MOUNTS.get(mount, {}).get("art")
        _mount_art_cache[mount] = load_image_safe(path) if path else None
    return _mount_art_cache[mount]


def play_queued_effects(manager, bindings):
    """Turns the rules' queued effect events into playing effects, per the
    skill_effects.csv bindings: each binding whose `on` matches the outcome
    (or is "always") plays on its anchor's tile(s)."""
    while EFFECT_EVENTS:
        event = EFFECT_EVENTS.pop(0)
        for binding in bindings.get(event["trigger"], []):
            if binding["on"] not in ("always", event["outcome"]):
                continue
            if binding["anchor"] == "recipients":
                tiles = event["recipients"]
            else:
                tiles = [event.get(binding["anchor"])]
            for tile in tiles:
                if tile is not None:
                    manager.play(binding["effect"], tile)


def draw_heavenly_light(surface, source, target, elapsed, zoom=1.0):
    """A shaft of light from `source` (the sun, or straight overhead) down
    onto `target`, pulsing, with a pool of light on the ground and - for
    its first SCENE_FLASH_MS - a blinding white flash over everything."""
    w, h = surface.get_size()
    layer = pygame.Surface((w, h), pygame.SRCALPHA)
    pulse = 0.85 + 0.15 * math.sin(elapsed / 180)
    grow = min(1.0, elapsed / 500)
    (sx, sy), (tx, ty) = source, target
    # Perpendicular to the beam, for its width at each end.
    length = max(1.0, math.hypot(tx - sx, ty - sy))
    px, py = -(ty - sy) / length, (tx - sx) / length
    for top_w, bottom_w, alpha in ((150, 70, 55), (90, 40, 90), (40, 16, 150)):
        top, bottom = top_w * zoom * grow, bottom_w * zoom * grow
        poly = [(sx + px * top, sy + py * top), (sx - px * top, sy - py * top),
                (tx - px * bottom, ty - py * bottom), (tx + px * bottom, ty + py * bottom)]
        pygame.draw.polygon(layer, (255, 248, 215, round(alpha * pulse)), poly)
    for radius, alpha in ((90, 50), (60, 80), (32, 130)):
        r = round(radius * zoom * grow)
        pygame.draw.ellipse(layer, (255, 250, 225, round(alpha * pulse)), (tx - r, ty - r // 2, r * 2, r))
    surface.blit(layer, (0, 0))
    if elapsed < SCENE_FLASH_MS:
        flash = pygame.Surface((w, h), pygame.SRCALPHA)
        flash.fill((255, 255, 245, round(235 * (1 - elapsed / SCENE_FLASH_MS))))
        surface.blit(flash, (0, 0))


def draw_despair_cloud(surface, cx, cy, zoom=1.0):
    """A small storm cloud hanging over a unit in Despair: puffs of dark
    grey, bobbing gently, with rain streaks falling from it."""
    now = pygame.time.get_ticks()
    bob = round(math.sin(now / 400) * 2 * zoom)
    w, h = round(40 * zoom), round(30 * zoom)
    cloud = pygame.Surface((w, h), pygame.SRCALPHA)
    puffs = [(0.28, 0.42, 0.2), (0.5, 0.32, 0.25), (0.72, 0.42, 0.19), (0.4, 0.5, 0.17), (0.6, 0.5, 0.17)]
    # Rain first, so the cloud sits over the top of it.
    fall = (now // 60) % max(1, round(8 * zoom))
    for i, rx in enumerate((0.3, 0.45, 0.6, 0.72)):
        x = round(w * rx)
        y = round(h * 0.6) + (fall + i * 3) % max(1, round(10 * zoom))
        pygame.draw.line(cloud, (120, 140, 170, 200), (x, y), (x - round(2 * zoom), y + round(5 * zoom)), max(1, round(zoom)))
    for fx, fy, fr in puffs:
        pygame.draw.circle(cloud, (40, 40, 52, 235), (round(w * fx), round(h * fy)), round(w * fr))
    for fx, fy, fr in puffs[:3]:
        pygame.draw.circle(cloud, (78, 78, 94, 235), (round(w * fx - w * 0.03), round(h * fy - h * 0.06)), round(w * fr * 0.6))
    surface.blit(cloud, (cx - w // 2, cy - h // 2 + bob))


def draw_mount(surface, unit, cx, cy, cell_w, cell_h, alpha=None):
    art = mount_art(unit.mount) if unit.mount else None
    if art is None:
        return
    spec = MOUNTS[unit.mount]
    width = max(1, round(cell_w * spec["width"]))
    height = max(1, round(width * art.get_height() / art.get_width()))
    scaled = pygame.transform.smoothscale(art, (width, height))
    if alpha is not None:
        scaled.set_alpha(alpha)
    saddle_x, saddle_y = spec["saddle"]
    surface.blit(scaled, (round(cx - width * saddle_x), round(cy + cell_h * spec["seat_y"] - height * saddle_y)))


def draw_unit(surface, sx, sy, unit, is_active=False, portraits=None, zoom=1.0, in_water=False, alpha=255):
    cx, cy = sx, sy + (TILE_HEIGHT // 2) - 12
    if in_water:
        cy += round(6 * zoom)

    cell_w = UNIT_SLOT_WIDTH * zoom * UNIT_CELL_FILL * UNIT_ART_SCALE
    cell_h = UNIT_SLOT_HEIGHT * zoom * UNIT_CELL_FILL * UNIT_ART_SCALE

    # Fading units (death animation) skip the tag/faith-bar/water-ripple
    # detail and just fade the portrait/silhouette out on its own - a dying
    # unit doesn't need its HUD chrome, and this keeps the fade path simple.
    fading = alpha < 255

    if not fading:
        # These HUD overlays (team tag, mini faith sliver) sit right at the
        # top of the unit's art, so their size/offset scale with
        # UNIT_ART_SCALE too, or they'd end up buried inside a bigger token.
        font = get_font(round(14 * UNIT_ART_SCALE))
        tag = "P" if unit.team == "Player" else "E"
        surface.blit(font.render(tag, True, (255, 255, 255)), (cx - round(4 * UNIT_ART_SCALE), cy - round(5 * UNIT_ART_SCALE)))
        bar_w, bar_h = round(30 * UNIT_ART_SCALE), round(4 * UNIT_ART_SCALE)
        bar_x, bar_y = cx - bar_w // 2, cy - round(22 * UNIT_ART_SCALE)
        pygame.draw.rect(surface, (60, 50, 10), (bar_x, bar_y, bar_w, bar_h))
        faith_pct = max(0, min(1, unit.faith / FAITH_CAP))
        pygame.draw.rect(surface, (255, 215, 0), (bar_x, bar_y, int(bar_w * faith_pct), bar_h))

    water_line = cy + round(10 * zoom)
    previous_clip = None
    if in_water and not fading:
        previous_clip = surface.get_clip()
        surface.set_clip(pygame.Rect(0, 0, surface.get_width(), max(0, water_line)))

    portrait = portraits.get(unit.name) if portraits is not None else None
    if portrait:
        pw, ph = portrait.get_size()
        scale = min(cell_w / pw, cell_h / ph)
        fit_size = (max(1, round(pw * scale)), max(1, round(ph * scale)))
        fitted_portrait = pygame.transform.smoothscale(portrait, fit_size)
        if fading:
            fitted_portrait.set_alpha(alpha)
        if unit.fallen:
            # Thrown to the ground: the riderless mount stands behind, and
            # the figure (without its stand) lies at its feet, head to the left.
            draw_mount(surface, unit, cx, cy, cell_w, cell_h, alpha if fading else None)
            figure = fitted_portrait.subsurface((0, 0, fitted_portrait.get_width(), round(fitted_portrait.get_height() * 0.72)))
            # Cropped to the figure itself: the token's transparent side
            # margins would otherwise become padding above and below it.
            figure = figure.subsurface(figure.get_bounding_rect())
            lying = pygame.transform.rotate(figure, 90)
            surface.blit(lying, lying.get_rect(midbottom=(cx + round(cell_w * 0.12), cy + round(cell_h * 0.42))))
        else:
            portrait_rect = fitted_portrait.get_rect(center=(cx, cy))
            surface.blit(fitted_portrait, portrait_rect)
            draw_mount(surface, unit, cx, cy, cell_w, cell_h, alpha if fading else None)
    else:
        radius = max(1, round(min(cell_w, cell_h) / 2))
        if fading:
            silhouette = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(silhouette, unit.color, (radius, radius), radius)
            pygame.draw.circle(silhouette, (255, 255, 255), (radius, radius), radius, 2)
            silhouette.set_alpha(alpha)
            surface.blit(silhouette, (cx - radius, cy - radius))
        else:
            pygame.draw.circle(surface, unit.color, (cx, cy), radius)
            pygame.draw.circle(surface, (255, 255, 255), (cx, cy), radius, 2)

    if in_water and not fading:
        # The clip above already sinks the unit's stand below the waterline;
        # no ripple ring on top - drawn over the figure it read as stray
        # blue lines across the unit.
        surface.set_clip(previous_clip)

    if unit.despair_turns > 0 and not fading:
        draw_despair_cloud(surface, cx, cy - round(cell_h / 2) - round(8 * zoom), zoom)

    if is_active and not fading:
        marker_y = cy - round(cell_h / 2) - 8
        pygame.draw.polygon(surface, (255, 60, 60), [(cx, marker_y), (cx - 5, marker_y - 7), (cx + 5, marker_y - 7)])


# A prop's footprint, as a fraction of the tile it stands on, and how much
# taller than its stated map height it is drawn. Unit standees are already
# drawn well out of scale with the map's own height units (see
# UNIT_ART_SCALE), so a tree drawn at exactly its map height reads as a
# shrub beside them - this lifts it back to a believable tree. Only the
# drawing is exaggerated: the prop's height in the map data is what the
# game rules and the map editor go by.
PROP_ART_SCALE = 1.9

# Each prop type's sprite builder, footprint (as a fraction of the tile's
# width) and how far below the tile's center its base sits - a tree's trunk
# is planted dead center, while a boulder's sprite bottoms out at the front
# corner of its diamond footprint, a quarter of its width below center
# (0.72 * TILE_WIDTH / 4 / TILE_HEIGHT - 0.5 = 0.36 - 0.5 + 0.5).
PROP_ART = {
    "tree": (build_tree_sprite, 0.62, 0.0),
    "boulder": (build_boulder_sprite, 0.72, 0.36),
}


_lit_prop_cache = {}


def draw_prop(surface, sx, sy, prop, zoom=1.0, light=1.0):
    """Draws a prop standing on the tile whose top corner is at (sx, sy),
    planted at the middle of that tile and its height scaled from the
    prop's own map height, so a taller prop really does stand taller on
    the board. `light` shades it to match the tile under it."""
    build_sprite, width_fill, sink = PROP_ART[prop["prop"]]
    sprite_height = max(1, round(prop["height"] * TILE_RISE * zoom * PROP_ART_SCALE))
    sprite_width = max(1, round(TILE_WIDTH * zoom * width_fill))
    # Seeded per tile so each prop's outline sits a little differently, and
    # so the same prop looks the same every frame.
    sprite = build_sprite(sprite_width, sprite_height, seed=prop["x"] * 31 + prop["y"])
    level = round(min(1.0, light) * 20) / 20
    if level < 1.0:
        cache_key = (id(sprite), level)
        lit = _lit_prop_cache.get(cache_key)
        if lit is None:
            lit = sprite.copy()
            shade = round(255 * level)
            lit.fill((shade, shade, min(255, shade + 12), 255), special_flags=pygame.BLEND_RGBA_MULT)
            _lit_prop_cache[cache_key] = lit
        sprite = lit
    base_x, base_y = sx, sy + TILE_HEIGHT * zoom * (0.5 + sink)
    surface.blit(sprite, (round(base_x - sprite_width / 2), round(base_y - sprite_height)))


async def main(stage=None, equipment_loadout=None, book_loadout=None, hero=None):
    global MAP_DATA, MAP_ROWS, MAP_COLS, SKILL_REGISTRY, ITEM_REGISTRY, EQUIPMENT_REGISTRY, BOOK_REGISTRY, CHARACTER_ROSTER, TERRAIN_LAYOUT, MAP_PROPS, PROP_TILES, ESCAPE_TILES

    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    if stage is None:
        required_files = ["map_layout.csv", "skills.csv", "items.csv", "equipment.csv", "characters.csv", "terrain_layout.csv", "game_settings.csv", "dialogues.csv"]
        if not all(os.path.exists(os.path.join(data_dir, filename)) for filename in required_files):
            generate_dummy_csv_files()

    invalid_assets = []
    try:
        MAP_DATA = load_map_from_csv(stage.get("map_layout") if stage else None)
    except (FileNotFoundError, OSError):
        seed = stage.get("node_id") if stage else None
        MAP_DATA = [[int(v) for v in line.split(",")] for line in generate_map_csv(8, 8, seed=seed).splitlines()]
    SKILL_REGISTRY = load_skills_from_csv()
    ITEM_REGISTRY = load_items_from_csv()
    EQUIPMENT_REGISTRY = load_equipment_from_csv()
    BOOK_REGISTRY = load_books_from_csv()
    CHARACTER_ROSTER = load_characters_from_csv(stage.get("characters") if stage else None)
    MAP_ROWS = len(MAP_DATA)
    MAP_COLS = len(MAP_DATA[0]) if MAP_DATA else 0

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    bring_window_to_front()
    pygame.display.set_caption(f"Tactics Engine: {stage['title']}" if stage else "Tactics Engine: Data Driven A* Pipeline")
    clock = pygame.time.Clock()
    font = get_font(22)
    big_font = get_font(96)
    music_ready = False
    try:
        music_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "bgmusic.ogg")
        pygame.mixer.music.load(music_path)
        pygame.mixer.music.set_volume(MUSIC_VOLUME)
        music_ready = True
    except (pygame.error, OSError):
        pass
    music_start_time = pygame.time.get_ticks() + 1000
    music_started = False
    # Reads each dialogue line aloud in its speaker's voice (see scripts/voices.py).
    dialogue_voice = DialogueVoice()

    assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
    attack_sound = None
    step_sound = None
    try:
        attack_sound = pygame.mixer.Sound(os.path.join(assets_dir, "sfx_attack.ogg"))
        attack_sound.set_volume(0.6)
        step_sound = pygame.mixer.Sound(os.path.join(assets_dir, "sfx_step.ogg"))
        step_sound.set_volume(0.5)
    except (pygame.error, OSError):
        pass

    origin_x = SCREEN_WIDTH // 2 - 80
    origin_y = SCREEN_HEIGHT // 4

    try:
        TERRAIN_LAYOUT = load_terrain_from_csv(stage.get("terrain_layout") if stage else None)
    except (FileNotFoundError, OSError):
        TERRAIN_LAYOUT = []
    if len(TERRAIN_LAYOUT) != MAP_ROWS or any(len(row) != MAP_COLS for row in TERRAIN_LAYOUT):
        theme = STAGE_THEMES.get(stage.get("node_id")) if stage else None
        weights = TERRAIN_THEMES.get(theme)
        TERRAIN_LAYOUT = load_terrain_from_text(generate_terrain_csv(MAP_ROWS, MAP_COLS, weights=weights))
    # A stage's scenery lives next to its other data files, like the map
    # editor's map_layers.csv does, rather than as another stages.csv column.
    props_path = os.path.join(os.path.dirname(stage["characters"]), "props.csv") if stage else None
    MAP_PROPS = load_props_from_csv(props_path)
    PROP_TILES = {(prop["x"], prop["y"]) for prop in MAP_PROPS}
    ESCAPE_TILES = load_escape_tiles_from_csv(os.path.join(os.path.dirname(props_path), "escape.csv") if props_path else None)
    props_by_tile = {(prop["x"], prop["y"]): prop for prop in MAP_PROPS}
    tile_lighting = compute_tile_lighting(MAP_DATA, props_by_tile)
    # Weather is a per-stage setting too, in weather.csv beside props.csv.
    weather_path = os.path.join(os.path.dirname(stage["characters"]), "weather.csv") if stage else None
    weather = Weather(load_weather_from_csv(weather_path), SCREEN_WIDTH, SCREEN_HEIGHT, seed=stage["node_id"] if stage else None)
    # Particle effects: the library (effects.csv) and what plays when (skill_effects.csv).
    effect_manager = EffectManager({name: EffectSpec(row) for name, row in load_effects_from_csv().items()})
    effect_bindings = load_skill_effects_from_csv()
    EFFECT_EVENTS.clear()
    SKILL_BANNERS.clear()
    CONVERT_FACES_USED.clear()

    settings = load_settings_from_csv()
    # A background picture is only used if game_settings.csv names one;
    # otherwise the battle is framed by a skybox matching the stage weather.
    background_path = settings.get("background_path", "").strip()
    skybox = Skybox(weather.kind, SCREEN_WIDTH, SCREEN_HEIGHT, seed=stage["node_id"] if stage else None)

    def spawn_units():
        spawned = [Unit(char_data) for char_data in CHARACTER_ROSTER]
        if equipment_loadout:
            for unit in spawned:
                unit.equipment = dict(equipment_loadout.get(unit.name, {}))
                apply_equipment_bonuses(unit, EQUIPMENT_REGISTRY)
        if book_loadout:
            for unit in spawned:
                progress = book_loadout.get(unit.name)
                if not progress:
                    continue
                unit.books = dict(progress.get("books", {}))
                unit.book_turns = dict(progress.get("turns", {}))
                unit.book_gain = dict(progress.get("gain", {}))
                apply_book_bonuses(unit, BOOK_REGISTRY)
                unit.level = progress.get("level", unit.level)
                unit.exp = progress.get("exp", unit.exp)
        for unit in spawned:
            apply_level_bonuses(unit)
        return spawned

    # The player's own character (from the new-game survey) joins the party.
    if hero:
        hero_entry = hero_character(hero, CHARACTER_ROSTER, MAP_DATA, PROP_TILES)
        if hero_entry:
            CHARACTER_ROSTER.append(hero_entry)

    units = spawn_units()
    # Faces already on the field aren't handed out again to converts.
    CONVERT_FACES_USED.update(u.face_portrait_path for u in units if u.face_portrait_path)
    # Only the Player side carries a satchel of supplies into battle.
    team_inventory = {"Player": {name: data["uses"] for name, data in ITEM_REGISTRY.items()}}
    dialogues = load_dialogues_from_csv(map_id=stage["node_id"] if stage else FIRST_STAGE_NODE)
    # Higher-detail portraits for HUD panels (turn order, action menu, unit
    # profile), independent of whatever art style the on-map token below
    # uses.
    face_portraits = build_character_face_portraits(units, invalid_assets)
    def build_map_art(for_units):
        if UNIT_ART_STYLE == "pixel":
            return build_character_pixel_art(for_units, invalid_assets)
        if UNIT_ART_STYLE == "chess":
            return build_character_chess_art(for_units, invalid_assets)
        return build_character_portraits(for_units, invalid_assets)

    map_art = build_map_art(units)
    # Which side each unit's art was last built for, so a unit changing
    # sides (conversion, turning back) gets its art rebuilt - e.g. the
    # converted Legionnaire portrait, or a light chess piece.
    art_built_for = {u.name: (u.team, u.portrait_path, u.face_portrait_path) for u in units}

    background_image = load_background_image(background_path, invalid_assets)
    terrain_image_cache = cache_terrain_images(TERRAIN_LAYOUT, invalid_assets)
    terrain_color_cache = cache_terrain_colors(terrain_image_cache)
    ui_frame = load_nine_slice_frame(invalid_assets)

    game_state = "TICKING"
    active_unit = None
    main_menu = ["Move", "Act", "Item", "Wait"]
    current_menu = main_menu
    menu_index = 0
    selected_skill = None
    selected_item = None
    cursor_x, cursor_y = 0, 0
    valid_tiles = []
    move_drag_start = None
    combat_log = "System Engine Initialized. Map loaded cleanly."
    rotation = 2
    map_zoom = 1.5
    active_projectile = None
    ai_pause_until = 0
    inspected_unit = None
    rotate_left_button = pygame.Rect(10, 205, 56, 32)
    rotate_right_button = pygame.Rect(76, 205, 56, 32)
    game_over_panel_rect = pygame.Rect(SCREEN_WIDTH // 2 - 450, SCREEN_HEIGHT // 2 - 250, 900, 500)
    game_over_content = frame_content_rect(game_over_panel_rect, ui_frame) if ui_frame else game_over_panel_rect.inflate(-32, -32)
    restart_button = pygame.Rect(game_over_content.centerx - 60, game_over_content.bottom - 60, 120, 40)
    stats_scroll = 0
    stats_panel_rect = pygame.Rect(10, 10, 280, 180)
    show_hud = True
    has_leader = any(unit.name == "Paul" for unit in units)
    dialogue_lines = dialogues.get(1, []) if has_leader else []
    stage_id = stage["node_id"] if stage else FIRST_STAGE_NODE
    # A scripted scene in progress ({"start", "leader", "spoken"}) and, once
    # it has played out, the stage's ending (see STAGE_SCENES).
    scene_state = None
    ending = None
    dialogue_index = 0
    dialogue_active = bool(dialogue_lines)
    # dialogues.csv can script mid-battle beats under later turn numbers (e.g.
    # Rome's persecution scene continues at turn 10/11); turn_counter tracks
    # how many units have taken a turn so far and is checked each time a new
    # one becomes active, so those beats actually fire instead of sitting
    # unreachable in the data.
    turn_counter = 1

    running = True
    while running:
        if music_ready and not music_started and pygame.time.get_ticks() >= music_start_time:
            pygame.mixer.music.play(-1)
            music_started = True

        if game_state == "TICKING" and scene_state is None and not dialogue_active and scene_due(stage_id, units):
            leader = next((u for u in units if u.name == LEADER_NAME and u.is_alive()), None)
            if leader:
                strike_down(leader)
            scene_state = {"start": pygame.time.get_ticks(), "leader": leader, "spoken": False}
            game_state = "SCENE"
            combat_log = "Suddenly a light from heaven flashes around Saul!"

        if game_state == "TICKING":
            living_units = [u for u in units if u.is_alive() and not u.disabled]
            for u in living_units:
                u.ct += u.speed
            ready = [u for u in living_units if u.ct >= 100]
            if ready and not dialogue_active:
                ready.sort(key=lambda u: u.ct, reverse=True)
                active_unit = ready[0]
                inspected_unit = active_unit
                turn_counter += 1
                pending_dialogue = dialogues.get(turn_counter) if has_leader else None
                if pending_dialogue:
                    dialogue_lines = pending_dialogue
                    dialogue_index = 0
                    dialogue_active = True
                    continue
                turn_start = begin_turn(active_unit, units)
                if turn_start["fled"]:
                    active_unit.ct = 0
                    combat_log = f"{active_unit.name} loses their nerve and flees the battle!"
                    game_state = "AI_PAUSE"
                    ai_pause_until = pygame.time.get_ticks() + AI_ACTION_DELAY_MS
                    continue
                snared_this_turn = turn_start["snared"]
                stunned_this_turn = turn_start["stunned"]
                despair_log = turn_start["despair_log"]
                lead_wore_off = turn_start["lead_wore_off"]
                cursor_x, cursor_y = active_unit.x, active_unit.y
                current_menu = get_action_menu(active_unit, units)
                menu_index = 0
                if despair_log:
                    active_unit.ct = 0
                    combat_log = despair_log
                    game_state = "AI_PAUSE"
                    ai_pause_until = pygame.time.get_ticks() + AI_ACTION_DELAY_MS
                elif stunned_this_turn:
                    active_unit.ct = 0
                    combat_log = f"{active_unit.name} is reeling and cannot act!"
                    game_state = "AI_PAUSE"
                    ai_pause_until = pygame.time.get_ticks() + AI_ACTION_DELAY_MS
                elif is_ai_team(active_unit.team) and (escape_plan := plan_escape(active_unit, units, snared_this_turn)):
                    combat_log = carry_out_escape(active_unit, escape_plan)
                    if step_sound:
                        step_sound.play()
                    active_unit.ct = 0
                    game_state = "AI_PAUSE"
                    ai_pause_until = pygame.time.get_ticks() + AI_ACTION_DELAY_MS
                elif is_ai_team(active_unit.team):
                    ai_choice = choose_ai_action(active_unit, units)
                    if ai_choice["action"] == "skip":
                        next_step = get_ai_move_destination(active_unit, units)
                        if next_step is not None and not active_unit.has_moved and not snared_this_turn:
                            active_unit.x, active_unit.y = next_step
                            if step_sound:
                                step_sound.play()
                            active_unit.has_moved = True
                            active_unit.ct = 0
                            combat_log = f"{active_unit.name} advances toward the enemy and ends the turn."
                            game_state = "AI_PAUSE"
                            ai_pause_until = pygame.time.get_ticks() + AI_ACTION_DELAY_MS
                        else:
                            active_unit.ct = 0
                            combat_log = f"{active_unit.name} has no more actions and ends the turn."
                            game_state = "AI_PAUSE"
                            ai_pause_until = pygame.time.get_ticks() + AI_ACTION_DELAY_MS
                    else:
                        rules = SKILL_REGISTRY[ai_choice["skill"]]
                        target_unit = ai_choice["target"]
                        active_unit.mp -= rules["mp_cost"]
                        active_unit.tp += 20 if rules["mp_cost"] > 0 else 10

                        if ai_choice["skill"] == "Shoot":
                            start_sx, start_sy = iso_to_screen(active_unit.x, active_unit.y, MAP_DATA[active_unit.y][active_unit.x], origin_x, origin_y, rotation, MAP_COLS, MAP_ROWS, map_zoom)
                            target_sx, target_sy = iso_to_screen(target_unit.x, target_unit.y, MAP_DATA[target_unit.y][target_unit.x], origin_x, origin_y, rotation, MAP_COLS, MAP_ROWS, map_zoom)
                            start_pos = (start_sx, start_sy + (TILE_HEIGHT // 2) - 12)
                            end_pos = (target_sx, target_sy + (TILE_HEIGHT // 2) - 12)
                            projectile_surf = create_projectile_surface(rules["color"], size=20)
                            active_projectile = {
                                "surface": projectile_surf,
                                "start": start_pos,
                                "end": end_pos,
                                "progress": 0.0,
                                "target": target_unit,
                                "attacker": active_unit,
                                "damage": rules["damage"],
                                "skill": ai_choice["skill"],
                                "direction": math.degrees(math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])),
                            }
                            combat_log = f"{active_unit.name} fires an arrow at {target_unit.name}!"
                            game_state = "PROJECTILE"
                            if attack_sound:
                                attack_sound.play()
                        elif rules["type"] == "Faith":
                            combat_log = resolve_faith_attack(active_unit, target_unit, ai_choice["skill"])
                            active_unit.has_acted = True
                            active_unit.ct = 0
                            game_state = "AI_PAUSE"
                            ai_pause_until = pygame.time.get_ticks() + AI_ACTION_DELAY_MS
                        elif rules["type"] == "Heal":
                            combat_log = apply_preach(active_unit, target_unit, ai_choice["skill"])
                            active_unit.has_acted = True
                            active_unit.ct = 0
                            game_state = "AI_PAUSE"
                            ai_pause_until = pygame.time.get_ticks() + AI_ACTION_DELAY_MS
                        elif rules["type"] == "Physical":
                            killed, combat_log = resolve_physical_hit(active_unit, target_unit, ai_choice["skill"], units)
                            if killed and attack_sound:
                                attack_sound.play()
                            active_unit.has_acted = True
                            active_unit.ct = 0
                            game_state = "AI_PAUSE"
                            ai_pause_until = pygame.time.get_ticks() + AI_ACTION_DELAY_MS
                        else:
                            if apply_skill_status(ai_choice["skill"], active_unit, target_unit, units):
                                combat_log = skill_status_message(ai_choice["skill"], active_unit, target_unit)
                            else:
                                combat_log = f"{active_unit.name} uses {ai_choice['skill']} on {target_unit.name}."
                            active_unit.has_acted = True
                            active_unit.ct = 0
                            game_state = "AI_PAUSE"
                            ai_pause_until = pygame.time.get_ticks() + AI_ACTION_DELAY_MS
                else:
                    if turn_start["disarmed"]:
                        combat_log = f"{active_unit.name} is disarmed and can't act this turn - only move or wait."
                    elif lead_wore_off:
                        combat_log = f"{active_unit.name}'s zeal from being led fades. (-{LEAD_LOVE_BONUS} Love)"
                    game_state = "MENU"
        elif game_state == "AI_PAUSE":
            if pygame.time.get_ticks() >= ai_pause_until:
                game_state = "TICKING"
        elif game_state == "SCENE":
            scene = STAGE_SCENES[stage_id]
            if not scene_state["spoken"] and pygame.time.get_ticks() - scene_state["start"] >= SCENE_LIGHT_MS:
                dialogue_lines = dialogues.get(scene["dialogue"], [])
                dialogue_index = 0
                dialogue_active = bool(dialogue_lines)
                scene_state["spoken"] = True
            elif scene_state["spoken"] and not dialogue_active:
                ending = scene
                game_state = "GAME_OVER"
                combat_log = "The road to Damascus ends in light."

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif dialogue_active:
                if ((event.type == pygame.KEYDOWN and event.key in [pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE])
                        or (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1)):
                    dialogue_index += 1
                    if dialogue_index >= len(dialogue_lines):
                        dialogue_active = False
                continue

            elif game_state == "GAME_OVER":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if restart_button.collidepoint(event.pos):
                        # Restart game
                        units = spawn_units()
                        game_state = "TICKING"
                        scene_state = None
                        ending = None
                        active_unit = None
                        current_menu = main_menu
                        menu_index = 0
                        selected_skill = None
                        selected_item = None
                        team_inventory = {"Player": {name: data["uses"] for name, data in ITEM_REGISTRY.items()}}
                        cursor_x, cursor_y = 0, 0
                        valid_tiles = []
                        combat_log = "Game restarted. Combat resumed."
                        rotation = 2
                        active_projectile = None
                elif event.type == pygame.KEYDOWN:
                    if event.key in [pygame.K_SPACE, pygame.K_RETURN]:
                        # Restart game with keyboard
                        units = spawn_units()
                        game_state = "TICKING"
                        scene_state = None
                        ending = None
                        active_unit = None
                        current_menu = main_menu
                        menu_index = 0
                        selected_skill = None
                        selected_item = None
                        team_inventory = {"Player": {name: data["uses"] for name, data in ITEM_REGISTRY.items()}}
                        cursor_x, cursor_y = 0, 0
                        valid_tiles = []
                        combat_log = "Game restarted. Combat resumed."
                        rotation = 2
                        active_projectile = None
                continue

            elif game_state == "PROJECTILE":
                continue

            elif event.type == pygame.MOUSEMOTION and game_state in ["MOVE_SELECT", "TARGET_SELECT"]:
                hit_tile = screen_to_map(event.pos[0], event.pos[1], origin_x, origin_y, MAP_DATA, rotation, map_zoom)
                if hit_tile is not None:
                    cursor_x, cursor_y = hit_tile

            elif (
                event.type == pygame.MOUSEBUTTONUP
                and event.button == 1
                and game_state == "MOVE_SELECT"
                and move_drag_start is not None
            ):
                # Completes a drag: mouse went down on the active unit (which
                # armed movement, see the MENU-click handler below) and is
                # now released over a different, valid tile. A plain click
                # (release back on the same tile it started from) intentionally
                # does nothing here, so click-then-click-elsewhere still works
                # via the ordinary MOVE_SELECT tile click below.
                hit_tile = screen_to_map(event.pos[0], event.pos[1], origin_x, origin_y, MAP_DATA, rotation, map_zoom)
                if hit_tile is not None and hit_tile != move_drag_start and hit_tile in valid_tiles:
                    active_unit.x, active_unit.y = hit_tile
                    if step_sound:
                        step_sound.play()
                    active_unit.has_moved = True
                    current_menu = get_action_menu(active_unit, units)
                    menu_index = 0
                    move_drag_start = None
                    game_state = "MENU"

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 4:  # Mouse wheel up
                    stats_scroll = max(0, stats_scroll - 1)
                elif event.button == 5:  # Mouse wheel down
                    stats_scroll += 1
                elif event.button == 1:
                    if rotate_left_button.collidepoint(event.pos):
                        rotation = (rotation - 1) % 4
                        combat_log = "Rotated map left."
                        continue
                    if rotate_right_button.collidepoint(event.pos):
                        rotation = (rotation + 1) % 4
                        combat_log = "Rotated map right."
                        continue
                if event.button == 3 and game_state in ["MOVE_SELECT", "TARGET_SELECT"]:
                    cursor_x, cursor_y = active_unit.x, active_unit.y
                    valid_tiles = []
                    if game_state == "MOVE_SELECT":
                        current_menu = main_menu
                        move_drag_start = None
                        game_state = "MENU"
                        combat_log = "Move canceled."
                    elif selected_item:
                        current_menu = [name for name, count in team_inventory.get(active_unit.team, {}).items() if count > 0] + ["Wait"]
                        game_state = "SUBMENU_ITEM"
                        selected_item = None
                        combat_log = "Item use canceled."
                    else:
                        current_menu = active_unit.skills + ["Wait"]
                        game_state = "SUBMENU_ACT"
                        selected_skill = None
                        combat_log = "Action canceled."
                    continue
                if event.button == 1 and game_state != "TICKING":
                    # Menu clicks (left-side HUD)
                    if game_state in ["MENU", "SUBMENU_ACT", "SUBMENU_ITEM"]:
                        item_height = 26
                        mx, my = event.pos
                        menu_panel_rect, menu_content = action_menu_layout(current_menu, ui_frame)
                        if menu_panel_rect.collidepoint(event.pos):
                            relative_y = my - (menu_content.y + 35)
                            if 0 <= relative_y < len(current_menu) * item_height:
                                clicked_index = int(relative_y // item_height)
                                if clicked_index < len(current_menu):
                                    menu_index = clicked_index
                                    choice = current_menu[menu_index]
                                    if game_state == "MENU":
                                        if choice == "Move" and not active_unit.has_moved and can_unit_move(active_unit, units):
                                            valid_tiles = get_valid_moves_a_star(active_unit, units)
                                            move_drag_start = (active_unit.x, active_unit.y)
                                            game_state = "MOVE_SELECT"
                                        elif choice == "Act" and not active_unit.has_acted:
                                            current_menu = active_unit.skills + ["Wait"]
                                            menu_index = 0
                                            game_state = "SUBMENU_ACT"
                                        elif choice == "Item" and not active_unit.has_acted:
                                            current_menu = [name for name, count in team_inventory.get(active_unit.team, {}).items() if count > 0] + ["Wait"]
                                            menu_index = 0
                                            game_state = "SUBMENU_ITEM"
                                        elif choice == "Wait":
                                            active_unit.ct = 0
                                            game_state = "TICKING"
                                    elif game_state == "SUBMENU_ACT":
                                        if current_menu[menu_index] == "Wait":
                                            active_unit.ct = 0
                                            game_state = "TICKING"
                                        else:
                                            skill_name = current_menu[menu_index]
                                            skill_rules = SKILL_REGISTRY[skill_name]
                                            if active_unit.mp >= skill_rules["mp_cost"]:
                                                selected_skill = skill_name
                                                valid_tiles = get_skill_targets(active_unit, skill_name, units)
                                                game_state = "TARGET_SELECT"
                                            else:
                                                combat_log = f"Failed! Requires {skill_rules['mp_cost']} MP."
                                    elif game_state == "SUBMENU_ITEM":
                                        if current_menu[menu_index] == "Wait":
                                            active_unit.ct = 0
                                            game_state = "TICKING"
                                        else:
                                            selected_item = current_menu[menu_index]
                                            valid_tiles = get_item_targets(active_unit, selected_item, units)
                                            game_state = "TARGET_SELECT"
                        else:
                            hit_tile = screen_to_map(mx, my, origin_x, origin_y, MAP_DATA, rotation, map_zoom)
                            if hit_tile is not None:
                                clicked_unit = find_unit_at_tile(units, *hit_tile)
                                if clicked_unit:
                                    inspected_unit = clicked_unit
                                    # Clicking the active unit directly (instead of
                                    # opening the menu and choosing "Move") arms it
                                    # for movement immediately - the player can then
                                    # either click a destination tile separately, or
                                    # keep the button held and drag straight there.
                                    if (
                                        game_state == "MENU"
                                        and clicked_unit is active_unit
                                        and clicked_unit.team == "Player"
                                        and not active_unit.has_moved
                                        and can_unit_move(active_unit, units)
                                    ):
                                        valid_tiles = get_valid_moves_a_star(active_unit, units)
                                        move_drag_start = (active_unit.x, active_unit.y)
                                        cursor_x, cursor_y = active_unit.x, active_unit.y
                                        game_state = "MOVE_SELECT"
                                        combat_log = f"{active_unit.name}: drag or click a highlighted tile to move."

                    # Tactical map clicks (tile selection)
                    elif game_state in ["MOVE_SELECT", "TARGET_SELECT"]:
                        hit_tile = screen_to_map(event.pos[0], event.pos[1], origin_x, origin_y, MAP_DATA, rotation, map_zoom)
                        if hit_tile is not None:
                            cursor_x, cursor_y = hit_tile
                            clicked_unit = find_unit_at_tile(units, *hit_tile)
                            if clicked_unit:
                                inspected_unit = clicked_unit
                            if game_state == "MOVE_SELECT" and hit_tile in valid_tiles:
                                active_unit.x, active_unit.y = hit_tile
                                if step_sound:
                                    step_sound.play()
                                active_unit.has_moved = True
                                current_menu = get_action_menu(active_unit, units)
                                menu_index = 0
                                move_drag_start = None
                                game_state = "MENU"
                            elif game_state == "TARGET_SELECT" and hit_tile in valid_tiles and selected_item:
                                target_unit = find_item_target(units, cursor_x, cursor_y, selected_item, active_unit.team)
                                if target_unit:
                                    combat_log = apply_item_effect(selected_item, active_unit, target_unit, units)
                                    team_inventory[active_unit.team][selected_item] -= 1
                                else:
                                    combat_log = f"{active_unit.name} used {selected_item}, but found no one to help."
                                active_unit.has_acted = True
                                selected_item = None
                                current_menu = get_action_menu(active_unit, units)
                                menu_index = 2
                                game_state = "MENU"
                            elif game_state == "TARGET_SELECT" and hit_tile in valid_tiles:
                                target_unit = next((u for u in units if u.x == cursor_x and u.y == cursor_y and u.is_alive()), None)
                                rules = SKILL_REGISTRY[selected_skill]
                                active_unit.mp -= rules["mp_cost"]
                                active_unit.tp += 20 if rules["mp_cost"] > 0 else 10
                                if selected_skill == "Shoot":
                                    start_sx, start_sy = iso_to_screen(active_unit.x, active_unit.y, MAP_DATA[active_unit.y][active_unit.x], origin_x, origin_y, rotation, MAP_COLS, MAP_ROWS, map_zoom)
                                    target_sx, target_sy = iso_to_screen(cursor_x, cursor_y, MAP_DATA[cursor_y][cursor_x], origin_x, origin_y, rotation, MAP_COLS, MAP_ROWS, map_zoom)
                                    start_pos = (start_sx, start_sy + (TILE_HEIGHT // 2) - 12)
                                    end_pos = (target_sx, target_sy + (TILE_HEIGHT // 2) - 12)
                                    projectile_surf = create_projectile_surface(rules["color"], size=20)
                                    active_projectile = {
                                        "surface": projectile_surf,
                                        "start": start_pos,
                                        "end": end_pos,
                                        "progress": 0.0,
                                        "target": target_unit,
                                        "attacker": active_unit,
                                        "damage": rules["damage"],
                                        "skill": selected_skill,
                                        "direction": math.degrees(math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])),
                                    }
                                    if target_unit:
                                        combat_log = f"{active_unit.name} fires an arrow at {target_unit.name}!"
                                    else:
                                        combat_log = f"{active_unit.name} fires an arrow at the ground."
                                    game_state = "PROJECTILE"
                                    if attack_sound:
                                        attack_sound.play()
                                else:
                                    if target_unit and rules["type"] == "Faith":
                                        combat_log = resolve_faith_attack(active_unit, target_unit, selected_skill)
                                    elif target_unit and rules["type"] == "Heal":
                                        combat_log = apply_preach(active_unit, target_unit, selected_skill)
                                    elif target_unit and rules["type"] == "Physical":
                                        killed, combat_log = resolve_physical_hit(active_unit, target_unit, selected_skill, units)
                                        if killed and attack_sound:
                                            attack_sound.play()
                                    elif target_unit:
                                        if apply_skill_status(selected_skill, active_unit, target_unit, units):
                                            combat_log = skill_status_message(selected_skill, active_unit, target_unit)
                                        else:
                                            combat_log = f"{active_unit.name} uses {selected_skill} on {target_unit.name}."
                                    else:
                                        combat_log = f"{active_unit.name} casted {selected_skill} but it missed the target field."
                                    active_unit.has_acted = True
                                    current_menu = get_action_menu(active_unit, units)
                                    menu_index = 2
                                    game_state = "MENU"

                    # Any other state: clicking a unit just inspects it
                    else:
                        hit_tile = screen_to_map(event.pos[0], event.pos[1], origin_x, origin_y, MAP_DATA, rotation, map_zoom)
                        if hit_tile is not None:
                            clicked_unit = find_unit_at_tile(units, *hit_tile)
                            if clicked_unit:
                                inspected_unit = clicked_unit

            # Handle map pan with ASWD keys (always available)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_h:
                    show_hud = not show_hud
                elif event.key == pygame.K_w:
                    origin_y -= 30
                    combat_log = "Map panned up."
                elif event.key == pygame.K_s:
                    origin_y += 30
                    combat_log = "Map panned down."
                elif event.key == pygame.K_a:
                    origin_x -= 30
                    combat_log = "Map panned left."
                elif event.key == pygame.K_d:
                    origin_x += 30
                    combat_log = "Map panned right."
                elif event.key == pygame.K_q:
                    rotation = (rotation - 1) % 4
                    combat_log = "Rotated map left."
                elif event.key == pygame.K_e:
                    rotation = (rotation + 1) % 4
                    combat_log = "Rotated map right."
                elif event.key == pygame.K_z:
                    map_zoom = min(2.0, map_zoom + 0.1)
                    combat_log = f"Zoom: {map_zoom:.1f}x"
                elif event.key == pygame.K_x:
                    map_zoom = max(0.5, map_zoom - 0.1)
                    combat_log = f"Zoom: {map_zoom:.1f}x"
                elif event.key == pygame.K_PAGEUP:
                    stats_scroll = max(0, stats_scroll - 1)
                    combat_log = "Stats scrolled up."
                elif event.key == pygame.K_PAGEDOWN:
                    stats_scroll += 1
                    combat_log = "Stats scrolled down."
                
                # Menu and grid keyboard controls (when not ticking)
                if game_state == "GAME_OVER":
                    if event.key in [pygame.K_SPACE, pygame.K_RETURN]:
                        # Already handled above
                        pass
                elif game_state not in ("TICKING", "MOVE_SELECT", "TARGET_SELECT"):
                    # Handle menu and grid keyboard controls (kept simple here)
                    if game_state in ["MENU", "SUBMENU_ACT", "SUBMENU_ITEM"]:
                        if event.key == pygame.K_UP:    menu_index = (menu_index - 1) % len(current_menu)
                        elif event.key == pygame.K_DOWN:  menu_index = (menu_index + 1) % len(current_menu)
                        elif event.key == pygame.K_ESCAPE:
                            if game_state == "SUBMENU_ACT":
                                current_menu = main_menu
                                menu_index = 1
                                game_state = "MENU"
                            elif game_state == "SUBMENU_ITEM":
                                current_menu = main_menu
                                menu_index = 2
                                selected_item = None
                                game_state = "MENU"
                            elif game_state == "MENU":
                                running = False
                        elif event.key == pygame.K_SPACE:
                            choice = current_menu[menu_index]
                            if game_state == "MENU":
                                if choice == "Move" and not active_unit.has_moved and can_unit_move(active_unit, units):
                                    valid_tiles = get_valid_moves_a_star(active_unit, units)
                                    move_drag_start = (active_unit.x, active_unit.y)
                                    game_state = "MOVE_SELECT"
                                elif choice == "Act" and not active_unit.has_acted:
                                    current_menu = active_unit.skills + ["Wait"]
                                    menu_index = 0
                                    game_state = "SUBMENU_ACT"
                                elif choice == "Item" and not active_unit.has_acted:
                                    current_menu = [name for name, count in team_inventory.get(active_unit.team, {}).items() if count > 0] + ["Wait"]
                                    menu_index = 0
                                    game_state = "SUBMENU_ITEM"
                                elif choice == "Wait":
                                    active_unit.ct = 0
                                    game_state = "TICKING"
                            elif game_state == "SUBMENU_ACT":
                                if current_menu[menu_index] == "Wait":
                                    active_unit.ct = 0
                                    game_state = "TICKING"
                                else:
                                    skill_name = current_menu[menu_index]
                                    skill_rules = SKILL_REGISTRY[skill_name]
                                    if active_unit.mp >= skill_rules["mp_cost"]:
                                        selected_skill = skill_name
                                        valid_tiles = get_skill_targets(active_unit, skill_name, units)
                                        game_state = "TARGET_SELECT"
                                    else:
                                        combat_log = f"Failed! Requires {skill_rules['mp_cost']} MP."
                            elif game_state == "SUBMENU_ITEM":
                                if current_menu[menu_index] == "Wait":
                                    active_unit.ct = 0
                                    game_state = "TICKING"
                                else:
                                    selected_item = current_menu[menu_index]
                                    valid_tiles = get_item_targets(active_unit, selected_item, units)
                                    game_state = "TARGET_SELECT"

                elif game_state in ["MOVE_SELECT", "TARGET_SELECT"]:
                    if event.key == pygame.K_UP and cursor_y > 0: cursor_y -= 1
                    elif event.key == pygame.K_DOWN and cursor_y < MAP_ROWS - 1: cursor_y += 1
                    elif event.key == pygame.K_LEFT and cursor_x > 0: cursor_x -= 1
                    elif event.key == pygame.K_RIGHT and cursor_x < MAP_COLS - 1: cursor_x += 1
                    elif event.key == pygame.K_ESCAPE:
                        cursor_x, cursor_y = active_unit.x, active_unit.y
                        valid_tiles = []
                        if game_state == "MOVE_SELECT":
                            current_menu = main_menu
                            move_drag_start = None
                            game_state = "MENU"
                            combat_log = "Move canceled."
                        elif selected_item:
                            current_menu = [name for name, count in team_inventory.get(active_unit.team, {}).items() if count > 0] + ["Wait"]
                            selected_item = None
                            game_state = "SUBMENU_ITEM"
                            combat_log = "Item use canceled."
                        else:
                            current_menu = active_unit.skills + ["Wait"]
                            selected_skill = None
                            game_state = "SUBMENU_ACT"
                            combat_log = "Action canceled."
                    elif event.key == pygame.K_SPACE:
                        if game_state == "MOVE_SELECT" and (cursor_x, cursor_y) in valid_tiles:
                            active_unit.x, active_unit.y = cursor_x, cursor_y
                            if step_sound:
                                step_sound.play()
                            active_unit.has_moved = True
                            current_menu = get_action_menu(active_unit, units)
                            menu_index = 0
                            move_drag_start = None
                            game_state = "MENU"
                        elif game_state == "TARGET_SELECT" and (cursor_x, cursor_y) in valid_tiles and selected_item:
                            target_unit = find_item_target(units, cursor_x, cursor_y, selected_item, active_unit.team)
                            if target_unit:
                                combat_log = apply_item_effect(selected_item, active_unit, target_unit, units)
                                team_inventory[active_unit.team][selected_item] -= 1
                            else:
                                combat_log = f"{active_unit.name} used {selected_item}, but found no one to help."
                            active_unit.has_acted = True
                            selected_item = None
                            current_menu = get_action_menu(active_unit, units)
                            menu_index = 2
                            game_state = "MENU"
                        elif game_state == "TARGET_SELECT" and (cursor_x, cursor_y) in valid_tiles:
                            target_unit = next((u for u in units if u.x == cursor_x and u.y == cursor_y and u.is_alive()), None)
                            rules = SKILL_REGISTRY[selected_skill]
                            active_unit.mp -= rules["mp_cost"]
                            active_unit.tp += 20 if rules["mp_cost"] > 0 else 10
                            if selected_skill == "Shoot":
                                start_sx, start_sy = iso_to_screen(active_unit.x, active_unit.y, MAP_DATA[active_unit.y][active_unit.x], origin_x, origin_y, rotation, MAP_COLS, MAP_ROWS, map_zoom)
                                target_sx, target_sy = iso_to_screen(cursor_x, cursor_y, MAP_DATA[cursor_y][cursor_x], origin_x, origin_y, rotation, MAP_COLS, MAP_ROWS, map_zoom)
                                start_pos = (start_sx, start_sy + (TILE_HEIGHT // 2) - 12)
                                end_pos = (target_sx, target_sy + (TILE_HEIGHT // 2) - 12)
                                projectile_surf = create_projectile_surface(rules["color"], size=20)
                                active_projectile = {
                                    "surface": projectile_surf,
                                    "start": start_pos,
                                    "end": end_pos,
                                    "progress": 0.0,
                                    "target": target_unit,
                                    "attacker": active_unit,
                                    "damage": rules["damage"],
                                    "skill": selected_skill,
                                    "direction": math.degrees(math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])),
                                }
                                combat_log = f"{active_unit.name} fires an arrow at {target_unit.name}!"
                                game_state = "PROJECTILE"
                                if attack_sound:
                                    attack_sound.play()
                            else:
                                if target_unit and rules["type"] == "Faith":
                                    combat_log = resolve_faith_attack(active_unit, target_unit, selected_skill)
                                elif target_unit and rules["type"] == "Heal":
                                    combat_log = apply_preach(active_unit, target_unit, selected_skill)
                                elif target_unit and rules["type"] == "Physical":
                                    killed, combat_log = resolve_physical_hit(active_unit, target_unit, selected_skill, units)
                                    if killed and attack_sound:
                                        attack_sound.play()
                                elif target_unit:
                                    if apply_skill_status(selected_skill, active_unit, target_unit, units):
                                        combat_log = skill_status_message(selected_skill, active_unit, target_unit)
                                    else:
                                        combat_log = f"{active_unit.name} uses {selected_skill} on {target_unit.name}."
                                else:
                                    combat_log = f"{active_unit.name} casted {selected_skill} but it missed the target field."
                                active_unit.has_acted = True
                                current_menu = get_action_menu(active_unit, units)
                                menu_index = 2
                                game_state = "MENU"

        winner = get_winner(units)
        if winner and game_state != "GAME_OVER":
            game_state = "GAME_OVER"
            combat_log = (f"{LEADER_NAME}'s faith is broken - the mission is lost!" if leader_faith_broken(units)
                          else f"{winner} team wins!")

        if game_state == "PROJECTILE" and active_projectile:
            active_projectile["progress"] += 0.05
            if active_projectile["progress"] >= 1.0:
                target_unit = active_projectile["target"]
                if target_unit and target_unit.is_alive():
                    _, combat_log = resolve_physical_hit(active_projectile["attacker"], target_unit, active_projectile["skill"], units)
                else:
                    combat_log = f"{active_projectile['attacker'].name}'s arrow fell short."
                active_projectile["attacker"].has_acted = True
                active_projectile["attacker"].ct = 0
                if is_ai_team(active_projectile["attacker"].team):
                    game_state = "AI_PAUSE"
                    ai_pause_until = pygame.time.get_ticks() + AI_ACTION_DELAY_MS
                else:
                    current_menu = get_action_menu(active_unit, units)
                    menu_index = 2
                    game_state = "MENU"
                active_projectile = None

        # --- DRAW ---
        changed = [u for u in units if art_built_for[u.name] != (u.team, u.portrait_path, u.face_portrait_path)]
        if changed:
            map_art.update(build_map_art(changed))
            face_portraits.update(build_character_face_portraits(changed, invalid_assets))
            for u in changed:
                art_built_for[u.name] = (u.team, u.portrait_path, u.face_portrait_path)
        if background_image:
            screen.blit(background_image, (0, 0))
            background_overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            background_overlay.fill((0, 0, 0, 125))
            screen.blit(background_overlay, (0, 0))
        else:
            skybox.draw(screen, rotation, origin_x, origin_y)

        for x, y in get_render_order(MAP_COLS, MAP_ROWS, rotation):
            z = MAP_DATA[y][x]
            sx, sy = iso_to_screen(x, y, z, origin_x, origin_y, rotation, MAP_COLS, MAP_ROWS, map_zoom)
            corner_offsets = tile_corner_offsets(MAP_DATA, x, y, rotation)
            base_val = round(90 + (z * 22))
            tile_color = [base_val, base_val, base_val]
            if game_state == "MOVE_SELECT" and (x, y) in valid_tiles:
                tile_color = [40, 110, 190]
            elif game_state == "TARGET_SELECT" and (x, y) in valid_tiles:
                if selected_item:
                    tile_color = list(ITEM_REGISTRY[selected_item]["color"])
                elif selected_skill:
                    tile_color = list(SKILL_REGISTRY[selected_skill]["color"])
            terrain_path = ""
            if y < len(TERRAIN_LAYOUT) and x < len(TERRAIN_LAYOUT[y]):
                terrain_path = TERRAIN_LAYOUT[y][x]
            terrain_image = terrain_image_cache.get(terrain_path)
            if terrain_image and terrain_path.lower().endswith("stone.png"):
                pygame.draw.polygon(screen, (125, 130, 142), tile_top_points(sx, sy, 1.0, corner_offsets))
            wall_color = terrain_color_cache.get(terrain_path)
            tile_light = tile_lighting.get((x, y), 1.0)
            top_pts = draw_iso_tile(screen, sx, sy, z, tuple(tile_color), terrain_image, map_zoom, wall_color=wall_color, corner_offsets=corner_offsets, light=tile_light)
            if game_state == "MOVE_SELECT" and (x, y) in valid_tiles:
                pygame.draw.polygon(screen, (30, 120, 255), top_pts)
                pygame.draw.polygon(screen, (255, 255, 255), top_pts, 2)
            elif game_state == "TARGET_SELECT" and (x, y) in valid_tiles:
                # The Act's (or item's) range: every tile it can be aimed at,
                # in translucent red over the terrain, pulsing gently.
                pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 250)
                pygame.gfxdraw.filled_polygon(screen, [(round(px), round(py)) for px, py in top_pts],
                                              (*TARGET_RANGE_COLOR, round(90 + 50 * pulse)))
                pygame.draw.polygon(screen, TARGET_RANGE_EDGE, top_pts, 2)
            elif (game_state == "TARGET_SELECT" and selected_skill == "Lead" and active_unit
                  and abs(x - active_unit.x) + abs(y - active_unit.y) <= LEAD_RADIUS):
                # Lead's area of effect, so it's clear who'll be led.
                pygame.gfxdraw.filled_polygon(screen, [(round(px), round(py)) for px, py in top_pts], (255, 200, 0, 90))
                pygame.draw.polygon(screen, (255, 225, 120), top_pts, 1)

            if game_state in ["MOVE_SELECT", "TARGET_SELECT"] and x == cursor_x and y == cursor_y:
                pygame.draw.polygon(screen, CURSOR_COLOR, top_pts, 3)

        # Second pass: props and units, back to front, over *all* the
        # terrain. Drawn in the same pass as the tiles, a taller tile in
        # front (a ridge, a hill) - or even a level one, since a unit's stand
        # reaches past its own tile - painted over the unit behind it.
        for x, y in get_render_order(MAP_COLS, MAP_ROWS, rotation):
            z = MAP_DATA[y][x]
            sx, sy = iso_to_screen(x, y, z, origin_x, origin_y, rotation, MAP_COLS, MAP_ROWS, map_zoom)
            terrain_path = TERRAIN_LAYOUT[y][x] if y < len(TERRAIN_LAYOUT) and x < len(TERRAIN_LAYOUT[y]) else ""
            tile_light = tile_lighting.get((x, y), 1.0)

            prop = props_by_tile.get((x, y))
            if prop:
                draw_prop(screen, sx, sy, prop, map_zoom, light=tile_light)

            for u in units:
                if u.x != x or u.y != y:
                    continue
                if u.is_alive():
                    draw_unit(screen, sx, sy, u, is_active=(u == active_unit), portraits=map_art, zoom=map_zoom, in_water=is_water_tile(terrain_path))
                    head_cy = sy + (TILE_HEIGHT // 2) - 12 + (round(6 * map_zoom) if is_water_tile(terrain_path) else 0)
                    now_ticks = pygame.time.get_ticks()
                    if u.converted_at is not None:
                        elapsed = now_ticks - u.converted_at
                        if 0 <= elapsed < CONVERT_FLASH_MS:
                            draw_conversion_flash(screen, sx, head_cy, elapsed)
                    if u.speech_bubble_until is not None:
                        if now_ticks < u.speech_bubble_until:
                            draw_speech_bubble(screen, sx, head_cy - round(35 * map_zoom), map_zoom)
                        else:
                            u.speech_bubble_until = None
                    if u.faith_popup is not None:
                        popup = u.faith_popup
                        popup_elapsed = now_ticks - popup["start"]
                        if popup_elapsed >= 0:
                            if popup_elapsed < FAITH_POPUP_MS:
                                draw_faith_popup(screen, sx, head_cy - round(35 * map_zoom), popup["amount"], popup_elapsed)
                            else:
                                u.faith_popup = None
                    if u.exp_popup is not None:
                        exp_elapsed = now_ticks - u.exp_popup["start"]
                        if exp_elapsed >= EXP_POPUP_MS:
                            u.exp_popup = None
                        elif exp_elapsed >= 0:
                            draw_exp_popup(screen, sx, head_cy - round(55 * map_zoom), u.exp_popup, exp_elapsed)
                elif u.removed_at is not None:
                    elapsed = pygame.time.get_ticks() - u.removed_at
                    if elapsed < DEATH_FADE_MS:
                        fade_alpha = max(0, 255 - int(255 * elapsed / DEATH_FADE_MS))
                        draw_unit(screen, sx, sy, u, portraits=map_art, zoom=map_zoom, alpha=fade_alpha)

        if game_state == "PROJECTILE" and active_projectile:
            prog = min(1.0, active_projectile["progress"])
            px = active_projectile["start"][0] + (active_projectile["end"][0] - active_projectile["start"][0]) * prog
            py = active_projectile["start"][1] + (active_projectile["end"][1] - active_projectile["start"][1]) * prog
            proj = pygame.transform.rotate(active_projectile["surface"], -active_projectile["direction"])
            rect = proj.get_rect(center=(px, py))
            screen.blit(proj, rect)

        play_queued_effects(effect_manager, effect_bindings)

        def effect_anchor(tile):
            tx, ty = tile
            ex, ey = iso_to_screen(tx, ty, MAP_DATA[ty][tx], origin_x, origin_y, rotation, MAP_COLS, MAP_ROWS, map_zoom)
            return ex, ey + TILE_HEIGHT * map_zoom / 2

        effect_manager.draw(screen, effect_anchor, map_zoom)

        if scene_state and scene_state["leader"]:
            leader = scene_state["leader"]
            lx, ly = iso_to_screen(leader.x, leader.y, MAP_DATA[leader.y][leader.x], origin_x, origin_y, rotation, MAP_COLS, MAP_ROWS, map_zoom)
            ground = (lx, ly + TILE_HEIGHT * map_zoom / 2)
            # From the sun when it's in view, else straight down from above.
            draw_heavenly_light(screen, skybox.sun_pos or (lx, -40), ground,
                                pygame.time.get_ticks() - scene_state["start"], map_zoom)

        # Over the battlefield, under the HUD.
        weather.draw(screen)

        if show_hud:
            draw_turn_order_queue(screen, font, predict_turn_order(units), face_portraits, 320, 10)

            # HUD
            pygame.draw.rect(screen, (40, 40, 50), (10, 10, 280, 180))
            pygame.draw.rect(screen, (100, 100, 110), (10, 10, 280, 180), 2)
            screen.blit(font.render("COMBATANT FIELD STATS (CT)", True, (220, 220, 220)), (20, 15))
            living_queue = sorted([u for u in units if u.is_alive()], key=lambda u: u.ct, reverse=True)
            max_visible_lines = 5
            max_scroll = max(0, len(living_queue) - max_visible_lines)
            stats_scroll = min(stats_scroll, max_scroll)
            for display_idx in range(max_visible_lines):
                actual_idx = stats_scroll + display_idx
                if actual_idx < len(living_queue):
                    u = living_queue[actual_idx]
                    col = (100, 180, 255) if u.team == "Player" else (255, 110, 110)
                    row_text = f"{u.name:9} Lv{u.level:<2} Faith:{round(u.faith):3} MP:{u.mp:2} CT:{u.ct}"
                    if u == active_unit: row_text += " *"
                    screen.blit(font.render(row_text, True, col), (20, 45 + (display_idx * 24)))

            pygame.draw.rect(screen, (30, 30, 40), rotate_left_button)
            pygame.draw.rect(screen, (30, 30, 40), rotate_right_button)
            pygame.draw.rect(screen, CURSOR_COLOR, rotate_left_button, 2)
            pygame.draw.rect(screen, CURSOR_COLOR, rotate_right_button, 2)
            screen.blit(font.render("<", True, (255, 255, 255)), (rotate_left_button.x + 20, rotate_left_button.y + 6))
            screen.blit(font.render(">", True, (255, 255, 255)), (rotate_right_button.x + 20, rotate_right_button.y + 6))
            screen.blit(font.render("Rotate", True, (220, 220, 220)), (rotate_left_button.x, rotate_left_button.y - 18))
            panel_height = 80 if invalid_assets else 60
            panel_rect = pygame.Rect(10, SCREEN_HEIGHT - panel_height, SCREEN_WIDTH - 20, panel_height)
            pygame.draw.rect(screen, (15, 15, 25), panel_rect)
            pygame.draw.rect(screen, (80, 180, 130), panel_rect, 1)
            previous_clip = screen.get_clip()
            screen.set_clip(panel_rect)
            screen.blit(font.render(f"ACTION LOG: {combat_log}", True, (50, 255, 180)), (25, panel_rect.y + 20))
            if invalid_assets:
                warning_text = f"Invalid assets: {len(invalid_assets)}"
                screen.blit(font.render(warning_text, True, (255, 200, 80)), (25, panel_rect.y + 40))
                for idx, (path, reason) in enumerate(invalid_assets[:2]):
                    screen.blit(font.render(f"{reason}: {os.path.basename(path)}", True, (255, 180, 120)), (25, panel_rect.y + 56 + idx * 16))
            screen.set_clip(previous_clip)

            preview_target = None
            if game_state == "TARGET_SELECT" and selected_skill and not selected_item and (cursor_x, cursor_y) in valid_tiles:
                preview_target = find_unit_at_tile(units, cursor_x, cursor_y)
            if preview_target:
                # FFT-style pre-attack readout in place of the profile box.
                draw_battle_preview(screen, font, active_unit, preview_target, selected_skill, units, face_portraits,
                                    (SCREEN_WIDTH // 2, panel_rect.y - 10))
            else:
                draw_unit_profile(screen, font, inspected_unit, face_portraits, (SCREEN_WIDTH - 10, panel_rect.y - 10))

        # Below the turn order queue, over everything but menus and dialogue.
        draw_skill_banner(screen, font, SCREEN_WIDTH // 2, 92)

        if game_state in ["MENU", "SUBMENU_ACT", "SUBMENU_ITEM"] and active_unit:
            draw_action_menu(screen, font, active_unit, current_menu, menu_index, units, team_inventory, ui_frame)

        if game_state == "GAME_OVER":
            is_victory = winner == "Player" or ending is not None
            theme_color = (255, 215, 0) if is_victory else (200, 60, 60)
            title_text = ending["title"] if ending else "VICTORY" if is_victory else "DEFEAT"
            subtitle_text = ending["subtitle"] if ending else (
                "Every heart in this land has turned toward the light."
                if is_victory else
                f"{LEADER_NAME}'s faith is broken. The road to Jerusalem ends here."
                if leader_faith_broken(units) else
                "The road to Jerusalem ends here."
            )

            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 190))
            screen.blit(overlay, (0, 0))

            if ui_frame:
                draw_nine_slice_panel(screen, game_over_panel_rect, ui_frame)
            else:
                pygame.draw.rect(screen, (15, 15, 25), game_over_panel_rect)
                pygame.draw.rect(screen, theme_color, game_over_panel_rect, 3)

            title_surf = big_font.render(title_text, True, theme_color)
            screen.blit(title_surf, title_surf.get_rect(center=(game_over_content.centerx, game_over_content.y + 80)))
            subtitle_surf = font.render(subtitle_text, True, (230, 230, 230))
            screen.blit(subtitle_surf, subtitle_surf.get_rect(center=(game_over_content.centerx, game_over_content.y + 160)))
            log_surf = font.render(combat_log, True, (190, 190, 190))
            screen.blit(log_surf, log_surf.get_rect(center=(game_over_content.centerx, game_over_content.y + 195)))
            if is_victory:
                thanks = get_font(40, bold=True).render(DEMO_THANKS, True, theme_color)
                screen.blit(thanks, thanks.get_rect(center=(game_over_content.centerx, game_over_content.y + 270)))
                detail = font.render(DEMO_THANKS_DETAIL, True, (230, 230, 230))
                screen.blit(detail, detail.get_rect(center=(game_over_content.centerx, game_over_content.y + 315)))

            pygame.draw.rect(screen, theme_color, restart_button)
            pygame.draw.rect(screen, (255, 255, 255), restart_button, 2)
            restart_label_color = (20, 20, 20) if is_victory else (255, 255, 255)
            restart_text = font.render("RESTART", True, restart_label_color)
            screen.blit(restart_text, restart_text.get_rect(center=restart_button.center))

        dialogue_voice.update(tuple(dialogue_lines[dialogue_index]) if dialogue_active else None)
        if dialogue_active:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            screen.blit(overlay, (0, 0))
            speaker, text = dialogue_lines[dialogue_index]
            draw_dialogue_window(screen, speaker, text, ui_frame)

        pygame.display.flip()
        clock.tick(60)
        await asyncio.sleep(0)

    # Book progress (turns held, reading level, accrued stat gain) is the
    # one piece of battle state that should survive back onto the world
    # map's persistent roster - equipment doesn't need this since it never
    # changes mid-battle.
    return {
        unit.name: {
            "books": dict(unit.books),
            "turns": dict(unit.book_turns),
            "gain": dict(unit.book_gain),
            "level": unit.level,
            "exp": unit.exp,
        }
        for unit in units
    }


# The opening battle: Saul riding to Damascus to arrest the disciples
# (Acts 9:1-2), before his conversion.
FIRST_STAGE_NODE = "damascus"


async def run_first_stage(hero=None):
    """Boots straight into the first stage's battle, skipping the world
    map. The world map (scripts/world_map.py) still works and is still
    reachable by running that module - the game's entrypoints just don't
    route through it while it's hidden."""
    return await main(load_stage_manifest().get(FIRST_STAGE_NODE), hero=hero)


if __name__ == '__main__':
    asyncio.run(run_first_stage())
    pygame.quit()
    sys.exit()

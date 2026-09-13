import os
import sys
import math
import heapq
import random
import asyncio
import pygame
from scripts.data_editor import (
    generate_dummy_csv_files,
    load_map_from_csv,
    load_skills_from_csv,
    load_items_from_csv,
    load_equipment_from_csv,
    load_books_from_csv,
    load_terrain_from_csv,
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
    BG_COLOR,
    CURSOR_COLOR,
    FAITH_CAP,
    CLASS_SKILLSETS,
)
from scripts.assets import (
    load_background_image,
    cache_terrain_images,
    cache_terrain_colors,
    build_character_portraits,
    build_character_face_portraits,
    build_character_chess_art,
    build_character_pixel_art,
    draw_tile_texture,
    create_projectile_surface,
    bring_window_to_front,
    load_nine_slice_frame,
    draw_nine_slice_panel,
    frame_content_rect,
    get_font,
)
from scripts.controls import screen_to_map

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
        self.mv = data["mv"]
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
        self.guarded = False
        self.disabled = False
        self.removed = False
        self.removed_at = None
        self.converted_at = None
        self.speech_bubble_until = None
        self.faith_popup = None
        self.magic_attack = data.get("magic_attack", 25)
        self.magic_defense = data.get("magic_defense", 25)
        self.faith = data.get("faith", 25)
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
                if (nx, ny) in occupied_tiles:
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
                if distance == 0 and not (skill_data["type"] == "Heal" or skill_name == "Defend"):
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
                (u for u in units_list if u.x == x and u.y == y and u.team == unit.team and u.is_alive() != wants_dead),
                None,
            )
            if occupant is not None:
                targets.append((x, y))
    return targets


def find_item_target(units_list, x, y, item_name, team):
    item_data = ITEM_REGISTRY[item_name]
    wants_dead = item_data["target_scope"] == "dead_ally"
    return next(
        (u for u in units_list if u.x == x and u.y == y and u.team == team and u.is_alive() != wants_dead),
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
    occupied = {(u.x, u.y) for u in units_list if u.is_alive() and u != target}
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


# Preach plays out as a beat, not an instant number change: both units get a
# "talking" speech bubble for PREACH_BUBBLE_MS, then it's replaced by the
# actual Faith gain floating up off the target for FAITH_POPUP_MS.
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


def draw_faith_popup(surface, cx, cy, amount, elapsed, duration=FAITH_POPUP_MS):
    progress = max(0.0, min(1.0, elapsed / duration))
    rise = round(30 * progress)
    alpha = max(0, 255 - int(255 * progress))
    font = get_font(24)
    sign = "+" if amount >= 0 else ""
    text = font.render(f"{sign}{amount} Faith", True, (255, 215, 0))
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
CLASS_PREACH_MULTIPLIER = {"Prophet": 1.5}
CLASS_SHOVE_DISTANCE = {"Sergeant": 3}
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
    return max(PHYSICAL_MIN_HIT_CHANCE, min(PHYSICAL_MAX_HIT_CHANCE, chance))


MORALE_CHANCE_SCALE = 0.004
MORALE_CHANCE_CAP = 0.3
MORALE_FAITH_BONUS = 5
MORALE_MV_BONUS = 1
MORALE_JUMP_BONUS = 1
MORALE_SPEED_BONUS = 5


def morale_buff_chance(unit):
    """Bravery's role: a chance, once per this unit's own turn, to catch a
    surge of morale - capped well short of certainty so it stays a nice
    bonus rather than something to build a whole strategy around."""
    return min(MORALE_CHANCE_CAP, unit.bravery * MORALE_CHANCE_SCALE)


def apply_morale_buff(unit):
    """Rolls for Bravery's morale-buff chance; on a hit, permanently boosts
    Faith, Move, Jump and Speed for the rest of the battle. Returns whether
    it triggered."""
    if random.random() >= morale_buff_chance(unit):
        return False
    unit.faith = min(FAITH_CAP, unit.faith + MORALE_FAITH_BONUS)
    unit.mv += MORALE_MV_BONUS
    unit.jump += MORALE_JUMP_BONUS
    unit.speed += MORALE_SPEED_BONUS
    return True


def resolve_physical_hit(attacker, target, skill_name, units_list=None):
    """Resolve a Physical-type skill's hit on a target. May miss outright
    (see physical_hit_chance); otherwise a guarded target blocks it
    (consuming the guard) instead of being removed. Returns
    (killed, message)."""
    if random.random() >= physical_hit_chance(attacker, target, units_list):
        return False, f"{attacker.name}'s {skill_name} misses {target.name}!"
    if target.guarded:
        target.guarded = False
        return False, f"{target.name} guards against {attacker.name}'s {skill_name} and holds their ground!"
    kill_unit(target)
    return True, f"{attacker.name} strikes down {target.name} with {skill_name}!"


def skill_status_message(skill_name, caster, target):
    if skill_name == "Shove":
        return f"{caster.name} shoves {target.name} back, leaving them reeling!"
    if skill_name == "Command":
        return f"{caster.name} commands {target.name}, hastening them into action!"
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


def apply_skill_status(skill_name, caster, target, units_list):
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
    return False


FAITH_TRANSFER_RATE = 0.2


def apply_preach(preacher, target):
    # Magic Attack represents spiritual power/conviction, channeled here
    # into stronger Preaching and Healing (both route through this
    # function) rather than a separate damage stat, since this game has no
    # damage-number combat to plug it into.
    effective_faith = preacher.faith + preacher.magic_attack
    gain = effective_faith * FAITH_TRANSFER_RATE * CLASS_PREACH_MULTIPLIER.get(preacher.char_class, 1.0)
    faith_before = target.faith
    target.faith = max(0, min(FAITH_CAP, target.faith + gain))
    actual_gain = target.faith - faith_before

    now = pygame.time.get_ticks()
    preacher.speech_bubble_until = now + PREACH_BUBBLE_MS
    target.speech_bubble_until = now + PREACH_BUBBLE_MS
    target.faith_popup = {"amount": round(actual_gain), "start": now + PREACH_BUBBLE_MS}

    if target.faith >= FAITH_CAP and target.team != "Player":
        target.team = "Player"
        target.color = (70, 140, 255)
        target.disabled = True
        target.converted_at = now + PREACH_BUBBLE_MS
        return f"{target.name}'s faith is complete! They lay down their arms and join the Player team."
    return f"{preacher.name} preaches to {target.name}, raising their faith to {round(target.faith)}!"


ANKH_MIN_REVIVE_FAITH = 10


def apply_item_effect(item_name, user, target, units_list=None):
    """Resolve a consumable item's effect on its target. Returns a combat
    log message. Each item's potency is tied to the user's own stats, the
    same way Preach scales off the preacher's Faith."""
    item_data = ITEM_REGISTRY[item_name]
    effect = item_data["effect"]
    amount = item_data["amount"]
    now = pygame.time.get_ticks()
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


def draw_dialogue_window(surface, font, speaker, text, frame=None):
    width, height = 1200, 340
    window = pygame.Rect(SCREEN_WIDTH // 2 - width // 2, SCREEN_HEIGHT - height - 40, width, height)
    if frame:
        draw_nine_slice_panel(surface, window, frame)
        content = frame_content_rect(window, frame)
    else:
        pygame.draw.rect(surface, (15, 15, 25), window)
        pygame.draw.rect(surface, CURSOR_COLOR, window, 2)
        content = pygame.Rect(window.x + 18, window.y + 14, window.width - 36, window.height - 28)

    surface.blit(font.render(speaker, True, CURSOR_COLOR), (content.x, content.y))

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
        surface.blit(font.render(line, True, (240, 240, 240)), (content.x, content.y + 32 + line_index * 22))
    surface.blit(font.render("[Space / Enter] Continue", True, (160, 160, 160)), (content.right - 210, content.bottom - 22))


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
    if unit.char_class:
        surface.blit(font.render(unit.char_class, True, (180, 180, 180)), (stats_x, py + 38))

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


def find_unit_at_tile(units, x, y):
    return next((u for u in units if u.is_alive() and u.x == x and u.y == y), None)


def get_winner(units):
    alive_teams = {u.team for u in units if u.is_alive()}
    if len(alive_teams) == 1:
        return next(iter(alive_teams))
    return None


AI_ACTION_DELAY_MS = 500


def is_ai_team(team):
    return str(team).lower() in {"enemy", "blue"}


def choose_ai_action(unit, units_list):
    allies = [u for u in units_list if u.is_alive() and u.team == unit.team]
    enemies = [u for u in units_list if u.is_alive() and u.team != unit.team]
    if not enemies and not allies:
        return {"action": "skip", "reason": "No units remain."}

    best_choice = None
    for skill_name in unit.skills:
        skill_data = SKILL_REGISTRY.get(skill_name)
        if not skill_data:
            continue
        if unit.mp < skill_data["mp_cost"]:
            continue

        if skill_data["type"] == "Heal":
            for ally in allies:
                if ally == unit or ally.faith >= FAITH_CAP:
                    continue
                distance = abs(unit.x - ally.x) + abs(unit.y - ally.y)
                if distance > skill_data["range"]:
                    continue
                candidate = {
                    "action": "skill",
                    "skill": skill_name,
                    "target": ally,
                    "priority": (ally.faith, distance),
                }
                if best_choice is None or candidate["priority"] < best_choice["priority"]:
                    best_choice = candidate
            continue

        if skill_data["type"] == "Support":
            for ally in allies:
                distance = abs(unit.x - ally.x) + abs(unit.y - ally.y)
                if distance > skill_data["range"]:
                    continue
                if skill_name == "Defend" and ally.guarded:
                    continue
                if skill_name == "Command" and ally == unit:
                    continue
                candidate = {
                    "action": "skill",
                    "skill": skill_name,
                    "target": ally,
                    "priority": (ally.ct, distance),
                }
                if best_choice is None or candidate["priority"] < best_choice["priority"]:
                    best_choice = candidate
            continue

        for enemy in enemies:
            distance = abs(unit.x - enemy.x) + abs(unit.y - enemy.y)
            if distance > skill_data["range"]:
                continue
            if distance == 0 and skill_data["type"] != "Heal":
                continue
            candidate = {
                "action": "skill",
                "skill": skill_name,
                "target": enemy,
                "priority": (-enemy.faith, -skill_data["damage"], distance),
            }
            if best_choice is None or candidate["priority"] < best_choice["priority"]:
                best_choice = candidate

    if best_choice is not None:
        return best_choice

    if not enemies:
        return {"action": "skip", "reason": "No enemies remain."}
    return {"action": "skip", "reason": "No valid attack or spell in range."}


def get_ai_move_destination(unit, units_list):
    allies = [u for u in units_list if u.is_alive() and u.team == unit.team]
    injured_allies = [u for u in allies if u.faith < FAITH_CAP and u != unit]
    enemies = [u for u in units_list if u.is_alive() and u.team != unit.team]
    if injured_allies and any(skill_name for skill_name in unit.skills if SKILL_REGISTRY.get(skill_name, {}).get("type") == "Heal"):
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
    screen_y = origin_y + (rx + ry) * (TILE_HEIGHT * zoom / 2) - (map_z * 14 * zoom)
    return screen_x, screen_y


# Every tile draws with at least this much visible side-wall "thickness,"
# even at height 0, so the map reads as a grid of resting cubes/blocks
# rather than flat painted diamonds. Elevation adds on top of this base.
TILE_DEPTH_BASE = 16


def draw_iso_tile(surface, sx, sy, height, color, terrain_image=None, zoom=1.0, wall_color=None):
    tile_width = TILE_WIDTH * zoom
    tile_height = TILE_HEIGHT * zoom
    h_offset = (height * 14 + TILE_DEPTH_BASE) * zoom
    top_points = [
        (sx, sy),
        (sx + tile_width / 2, sy + tile_height / 2),
        (sx, sy + tile_height),
        (sx - tile_width / 2, sy + tile_height / 2)
    ]
    wall_base = wall_color if wall_color is not None else color
    left_wall = [top_points[3], top_points[2], (top_points[2][0], top_points[2][1] + h_offset), (top_points[3][0], top_points[3][1] + h_offset)]
    pygame.draw.polygon(surface, (int(wall_base[0]*0.5), int(wall_base[1]*0.5), int(wall_base[2]*0.5)), left_wall)
    right_wall = [top_points[2], top_points[1], (top_points[1][0], top_points[1][1] + h_offset), (top_points[2][0], top_points[2][1] + h_offset)]
    pygame.draw.polygon(surface, (int(wall_base[0]*0.7), int(wall_base[1]*0.7), int(wall_base[2]*0.7)), right_wall)

    if terrain_image:
        image = pygame.transform.smoothscale(terrain_image, (round(tile_width), round(tile_height)))
        surface.blit(image, (round(sx - tile_width / 2), round(sy)))
    else:
        pygame.draw.polygon(surface, color, top_points)
        draw_tile_texture(surface, top_points, height, color)

    return top_points


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
# Which art the on-map token uses: "pixel" (small FFT-style chibi pixel-art
# sprites, by job class - see build_character_pixel_art), "chess" (classic
# chess pieces, tried and reverted - too literal), or "icons" (each
# character's own small sprite, the original look).
UNIT_ART_STYLE = "pixel"


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
        portrait_rect = fitted_portrait.get_rect(center=(cx, cy))
        surface.blit(fitted_portrait, portrait_rect)
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
        surface.set_clip(previous_clip)
        ripple_w = max(10, round(cell_w * 0.5))
        pygame.draw.ellipse(surface, (150, 210, 240), (cx - ripple_w // 2, water_line - 4, ripple_w, 8), 2)

    if is_active and not fading:
        marker_y = cy - round(cell_h / 2) - 8
        pygame.draw.polygon(surface, (255, 60, 60), [(cx, marker_y), (cx - 5, marker_y - 7), (cx + 5, marker_y - 7)])


async def main(stage=None, equipment_loadout=None, book_loadout=None):
    global MAP_DATA, MAP_ROWS, MAP_COLS, SKILL_REGISTRY, ITEM_REGISTRY, EQUIPMENT_REGISTRY, BOOK_REGISTRY, CHARACTER_ROSTER, TERRAIN_LAYOUT

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
        pygame.mixer.music.set_volume(0.5)
        music_ready = True
    except (pygame.error, OSError):
        pass
    music_start_time = pygame.time.get_ticks() + 1000
    music_started = False

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
    settings = load_settings_from_csv()
    background_path = settings.get("background_path", "").strip()
    if not background_path:
        background_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "bg.jpg")

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
        return spawned

    units = spawn_units()
    # Only the Player side carries a satchel of supplies into battle.
    team_inventory = {"Player": {name: data["uses"] for name, data in ITEM_REGISTRY.items()}}
    dialogues = load_dialogues_from_csv(map_id=stage["node_id"] if stage else "jerusalem")
    portraits = build_character_portraits(units, invalid_assets)
    # Higher-detail portraits for HUD panels (turn order, action menu, unit
    # profile), independent of whatever art style the on-map token below
    # uses.
    face_portraits = build_character_face_portraits(units, invalid_assets)
    if UNIT_ART_STYLE == "pixel":
        map_art = build_character_pixel_art(units, invalid_assets)
    elif UNIT_ART_STYLE == "chess":
        map_art = build_character_chess_art(units, invalid_assets)
    else:
        map_art = portraits

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
    has_jesus = any(unit.name == "Jesus" for unit in units)
    dialogue_lines = dialogues.get(1, []) if has_jesus else []
    dialogue_index = 0
    dialogue_active = bool(dialogue_lines)
    # dialogues.csv can script mid-battle beats under later turn numbers (e.g.
    # Jerusalem's arrest scene continues at turn 10/11); turn_counter tracks
    # how many units have taken a turn so far and is checked each time a new
    # one becomes active, so those beats actually fire instead of sitting
    # unreachable in the data.
    turn_counter = 1

    running = True
    while running:
        if music_ready and not music_started and pygame.time.get_ticks() >= music_start_time:
            pygame.mixer.music.play(-1)
            music_started = True

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
                pending_dialogue = dialogues.get(turn_counter) if has_jesus else None
                if pending_dialogue:
                    dialogue_lines = pending_dialogue
                    dialogue_index = 0
                    dialogue_active = True
                    continue
                active_unit.has_moved = False
                active_unit.has_acted = False
                apply_book_growth(active_unit, BOOK_REGISTRY)
                apply_morale_buff(active_unit)
                snared_this_turn = active_unit.snared_turns > 0
                if snared_this_turn:
                    active_unit.snared_turns -= 1
                stunned_this_turn = active_unit.stunned_turns > 0
                if stunned_this_turn:
                    active_unit.stunned_turns -= 1
                active_unit.faith = max(0, active_unit.faith - active_unit.faith * 0.01)
                cursor_x, cursor_y = active_unit.x, active_unit.y
                current_menu = get_action_menu(active_unit, units)
                menu_index = 0
                if stunned_this_turn:
                    active_unit.ct = 0
                    combat_log = f"{active_unit.name} is reeling and cannot act!"
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
                            combat_log = apply_preach(active_unit, target_unit)
                            active_unit.has_acted = True
                            active_unit.ct = 0
                            game_state = "AI_PAUSE"
                            ai_pause_until = pygame.time.get_ticks() + AI_ACTION_DELAY_MS
                        elif rules["type"] == "Heal":
                            combat_log = apply_preach(active_unit, target_unit)
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
                    game_state = "MENU"
        elif game_state == "AI_PAUSE":
            if pygame.time.get_ticks() >= ai_pause_until:
                game_state = "TICKING"

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
                                        combat_log = apply_preach(active_unit, target_unit)
                                    elif target_unit and rules["type"] == "Heal":
                                        combat_log = apply_preach(active_unit, target_unit)
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
                                    combat_log = apply_preach(active_unit, target_unit)
                                elif target_unit and rules["type"] == "Heal":
                                    combat_log = apply_preach(active_unit, target_unit)
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
            combat_log = f"{winner} team wins!"

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
        if background_image:
            screen.blit(background_image, (0, 0))
            background_overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            background_overlay.fill((0, 0, 0, 125))
            screen.blit(background_overlay, (0, 0))
        else:
            screen.fill(BG_COLOR)

        for x, y in get_render_order(MAP_COLS, MAP_ROWS, rotation):
            z = MAP_DATA[y][x]
            sx, sy = iso_to_screen(x, y, z, origin_x, origin_y, rotation, MAP_COLS, MAP_ROWS, map_zoom)
            base_val = 90 + (z * 22)
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
                pygame.draw.polygon(screen, (125, 130, 142), [
                    (sx, sy),
                    (sx + TILE_WIDTH // 2, sy + TILE_HEIGHT // 2),
                    (sx, sy + TILE_HEIGHT),
                    (sx - TILE_WIDTH // 2, sy + TILE_HEIGHT // 2),
                ])
            wall_color = terrain_color_cache.get(terrain_path)
            top_pts = draw_iso_tile(screen, sx, sy, z, tuple(tile_color), terrain_image, map_zoom, wall_color=wall_color)
            if game_state == "MOVE_SELECT" and (x, y) in valid_tiles:
                pygame.draw.polygon(screen, (30, 120, 255), top_pts)
                pygame.draw.polygon(screen, (255, 255, 255), top_pts, 2)

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
                elif u.removed_at is not None:
                    elapsed = pygame.time.get_ticks() - u.removed_at
                    if elapsed < DEATH_FADE_MS:
                        fade_alpha = max(0, 255 - int(255 * elapsed / DEATH_FADE_MS))
                        draw_unit(screen, sx, sy, u, portraits=map_art, zoom=map_zoom, alpha=fade_alpha)

            if game_state in ["MOVE_SELECT", "TARGET_SELECT"] and x == cursor_x and y == cursor_y:
                pygame.draw.polygon(screen, CURSOR_COLOR, top_pts, 3)

        if game_state == "PROJECTILE" and active_projectile:
            prog = min(1.0, active_projectile["progress"])
            px = active_projectile["start"][0] + (active_projectile["end"][0] - active_projectile["start"][0]) * prog
            py = active_projectile["start"][1] + (active_projectile["end"][1] - active_projectile["start"][1]) * prog
            proj = pygame.transform.rotate(active_projectile["surface"], -active_projectile["direction"])
            rect = proj.get_rect(center=(px, py))
            screen.blit(proj, rect)

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
                    row_text = f"{u.name:9} Faith:{round(u.faith):3} MP:{u.mp:2} CT:{u.ct}"
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

            draw_unit_profile(screen, font, inspected_unit, face_portraits, (SCREEN_WIDTH - 10, panel_rect.y - 10))

        if game_state in ["MENU", "SUBMENU_ACT", "SUBMENU_ITEM"] and active_unit:
            draw_action_menu(screen, font, active_unit, current_menu, menu_index, units, team_inventory, ui_frame)

        if game_state == "GAME_OVER":
            is_victory = winner == "Player"
            theme_color = (255, 215, 0) if is_victory else (200, 60, 60)
            title_text = "VICTORY" if is_victory else "DEFEAT"
            subtitle_text = (
                "Every heart in this land has turned toward the light."
                if is_victory else
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

            pygame.draw.rect(screen, theme_color, restart_button)
            pygame.draw.rect(screen, (255, 255, 255), restart_button, 2)
            restart_label_color = (20, 20, 20) if is_victory else (255, 255, 255)
            restart_text = font.render("RESTART", True, restart_label_color)
            screen.blit(restart_text, restart_text.get_rect(center=restart_button.center))

        if dialogue_active:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            screen.blit(overlay, (0, 0))
            speaker, text = dialogue_lines[dialogue_index]
            draw_dialogue_window(screen, font, speaker, text, ui_frame)

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
        }
        for unit in units
    }


if __name__ == '__main__':
    asyncio.run(main())
    pygame.quit()
    sys.exit()

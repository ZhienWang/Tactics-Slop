"""Headless play-test simulator: runs many battles on each stage using the
game's own rules - no window, no animations, no waiting - and reports
balance numbers (win rate, battle length, conversions, losses, EXP pace...).

How it works: it runs the same turn loop as a battle (CT ticking,
begin_turn upkeep, move-or-act) and calls the game's real rule functions
and enemy AI. The Player side is played by a script too - by default a
"human-like" policy (preach to convert first, Slash-disarm archers, heal
only allies below half faith), or the enemy AI itself with --player-ai game.

Treat the results as direction, not truth: a scripted player can't judge
fun or feel, and makes simpler choices than a person. It's good at finding
imbalances - a dominant strategy, a stat that snowballs, a stage that drags.

Run from the project root:
    python tools/playtest_sim.py                      # every stage, 40 battles each
    python tools/playtest_sim.py --runs 100 --stages jerusalem,rome
    python tools/playtest_sim.py --player-ai game     # let the enemy AI play your side

If the battle loop's turn logic in scripts/game_logic.py changes (what happens
at turn start, how actions resolve), mirror it in run_battle below;
scripts/test_playtest_sim.py checks the two still run together.
"""
import argparse
import collections
import contextlib
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

import scripts.game_logic as g  # noqa: E402
from scripts.data_editor import (  # noqa: E402
    load_books_from_csv, load_characters_from_csv, load_escape_tiles_from_csv, load_equipment_from_csv, load_items_from_csv,
    load_map_from_csv, load_props_from_csv, load_skills_from_csv, load_stage_manifest, load_terrain_from_csv,
)

# Roughly how long each side's turn takes in real play, for the play-time
# estimate: enemy turns are the AI pause, player turns a person deciding.
ENEMY_TURN_SECONDS = 0.5
PLAYER_TURN_SECONDS = 6


# --- the scripted player -------------------------------------------------------

def human_like_score(game_score):
    """A Player-side policy closer to how a person plays than the enemy AI
    is: go for conversions, disarm shooters first, and only heal allies who
    are actually hurting. The enemy side keeps the game's own scoring."""
    def score(unit, skill_name, skill_data, target, distance, units_list):
        if unit.team != "Player":
            return game_score(unit, skill_name, skill_data, target, distance, units_list)
        kind = skill_data["type"]
        if g.ESCAPE_TILES and target.char_class in g.ESCAPING_CLASSES and target.team != "Player":
            # A disciple running for the exits: net them first, else preach.
            if skill_name == "Fish net":
                return None if target.snared_turns > 0 else 95
            if kind == "Faith":
                return 85
        if kind == "Heal":
            if target is unit or target.faith >= g.FAITH_CAP * 0.5:
                return None
            return 75
        if kind == "Physical" and skill_name in g.DISARM_SKILLS:
            if target.disarmed_turns > 0:
                return None
            return 80 if "Shoot" in target.skills else 40
        if kind == "Faith":
            return 60 + 20 * target.faith / g.FAITH_CAP
        return game_score(unit, skill_name, skill_data, target, distance, units_list)
    return score


# Whether the Player side moves like a person - riding its full Move toward
# the enemy and then acting - rather than the enemy AI's one step a turn.
HUMAN_MOVES = False


def human_move(unit, units):
    """Rides as far as it can toward the nearest enemy, making for any
    disciple running for the exits first."""
    enemies = [u for u in units if g.targetable(u) and u.team != unit.team]
    if not enemies:
        return
    runners = [u for u in enemies if g.ESCAPE_TILES and u.char_class in g.ESCAPING_CLASSES and u.snared_turns == 0]
    dist = lambda a, b: abs(a[0] - b.x) + abs(a[1] - b.y)
    target = min(runners or enemies, key=lambda u: dist((unit.x, unit.y), u))
    unit.x, unit.y = min(g.get_valid_moves_a_star(unit, units), key=lambda t: dist(t, target))
    unit.has_moved = True


@contextlib.contextmanager
def player_policy(name):
    """Swaps the Player side's decision-making in for the duration of a
    simulation only, so importing this module never changes the game."""
    global HUMAN_MOVES
    original = g.score_ai_candidate
    if name == "human":
        g.score_ai_candidate = human_like_score(original)
        HUMAN_MOVES = True
    try:
        yield
    finally:
        g.score_ai_candidate = original
        HUMAN_MOVES = False


# --- one battle ----------------------------------------------------------------

def load_stage(stage):
    g.MAP_DATA = load_map_from_csv(stage["map_layout"])
    g.MAP_ROWS, g.MAP_COLS = len(g.MAP_DATA), len(g.MAP_DATA[0])
    g.SKILL_REGISTRY = load_skills_from_csv()
    g.ITEM_REGISTRY = load_items_from_csv()
    g.EQUIPMENT_REGISTRY = load_equipment_from_csv()
    g.BOOK_REGISTRY = load_books_from_csv()
    g.CHARACTER_ROSTER = load_characters_from_csv(stage["characters"])
    g.TERRAIN_LAYOUT = load_terrain_from_csv(stage["terrain_layout"])
    g.MAP_PROPS = load_props_from_csv(os.path.join(os.path.dirname(stage["characters"]), "props.csv"))
    g.PROP_TILES = {(p["x"], p["y"]) for p in g.MAP_PROPS}
    g.ESCAPE_TILES = load_escape_tiles_from_csv(os.path.join(os.path.dirname(stage["characters"]), "escape.csv"))


def run_battle(stage, seed, max_turns=400):
    """Plays one battle to the end (or max_turns unit-turns). Returns
    (winner or "timeout", unit-turns played, Counter of stats)."""
    random.seed(seed)
    load_stage(stage)
    g.EFFECT_EVENTS.clear()
    units = [g.Unit(c) for c in g.CHARACTER_ROSTER]
    for u in units:
        g.apply_level_bonuses(u)
    party = {c["name"] for c in g.CHARACTER_ROSTER if c["team"] == "Player"}
    stats = collections.Counter()
    turns = 0

    while turns < max_turns and not g.get_winner(units):
        if g.scene_due(stage["node_id"], units):
            # The stage's scripted scene ends the battle (see STAGE_SCENES).
            stats["scene"] += 1
            break
        living = [u for u in units if u.is_alive() and not u.disabled]
        if not living:
            break
        for u in living:
            u.ct += u.speed
        ready = [u for u in living if u.ct >= 100]
        if not ready:
            continue
        unit = max(ready, key=lambda u: u.ct)
        turns += 1
        stats[f"turns_{unit.team}"] += 1

        morale_before = unit.morale_used
        start = g.begin_turn(unit, units)
        stats["morale"] += unit.morale_used and not morale_before
        if start["fled"]:
            unit.ct = 0
            continue
        if start["despair_log"] or start["stunned"]:
            stats["turns_lost_despair" if start["despair_log"] else "turns_lost_stun"] += 1
            unit.ct = 0
            continue
        if start["disarmed"]:
            stats[f"turns_disarmed_{unit.team}"] += 1

        if g.is_ai_team(unit.team) and (plan := g.plan_escape(unit, units, start["snared"])):
            g.carry_out_escape(unit, plan)
            stats["escaped"] += plan["escapes"]
            unit.ct = 0
            continue

        choice = g.choose_ai_action(unit, units)
        if choice["action"] == "skip" and HUMAN_MOVES and unit.team == "Player" and not start["snared"]:
            human_move(unit, units)
            choice = g.choose_ai_action(unit, units)
            if choice["action"] == "skip":
                unit.ct = 0
                continue
        if choice["action"] == "skip":
            step = g.get_ai_move_destination(unit, units)
            if step is not None and not start["snared"]:
                unit.x, unit.y = step
            unit.ct = 0
            continue

        skill, target = choice["skill"], choice["target"]
        rules = g.SKILL_REGISTRY[skill]
        unit.mp -= rules["mp_cost"]
        stats[f"act_{unit.team}_{skill}"] += 1
        if rules["type"] == "Faith":
            g.resolve_faith_attack(unit, target, skill)
        elif rules["type"] == "Heal":
            g.apply_preach(unit, target, skill)
        elif rules["type"] == "Physical":
            killed, _ = g.resolve_physical_hit(unit, target, skill, units)
            stats[f"kills_by_{unit.team}"] += killed
        else:
            g.apply_skill_status(skill, unit, target, units)
        unit.ct = 0

    for event in g.EFFECT_EVENTS:
        stats[f"event_{event['trigger']}_{event['outcome']}"] += 1
    players = [u for u in units if u.name in party]
    stats["party_size"] = len(players)
    stats["party_survivors"] = sum(1 for u in players if u.is_alive())
    stats["party_levels"] = sum(u.level for u in players)
    stats["best_level"] = max((u.level for u in players), default=1)
    stats["enemies"] = sum(1 for c in g.CHARACTER_ROSTER if c["team"] != "Player")
    # Enemies fighting for the Player at the end (conversions can be undone),
    # and how many fled the field.
    stats["converted"] = sum(1 for u in units if u.converted and u.is_alive())
    stats["fled"] = sum(1 for u in units if u.fled)
    return ("Player" if stats["scene"] else g.get_winner(units)) or "timeout", turns, stats


# --- report --------------------------------------------------------------------

def simulate_stage(node, stage, runs, max_turns, policy):
    outcomes = collections.Counter()
    total = collections.Counter()
    lengths = []
    with player_policy(policy):
        for seed in range(runs):
            winner, turns, stats = run_battle(stage, seed, max_turns)
            outcomes[winner] += 1
            total.update(stats)
            lengths.append(turns)
    avg = {k: v / runs for k, v in total.items()}
    minutes = (avg.get("turns_Enemy", 0) * ENEMY_TURN_SECONDS + avg.get("turns_Player", 0) * PLAYER_TURN_SECONDS) / 60
    preach = {k[len("event_Preach_"):]: v for k, v in avg.items() if k.startswith("event_Preach_")}
    preach_tries = preach.get("hit", 0) + preach.get("convert", 0) + preach.get("miss", 0)
    actions = {k[len("act_"):]: round(v, 1) for k, v in sorted(avg.items()) if k.startswith("act_")}
    row = {
        "stage": node,
        "win": outcomes["Player"] / runs,
        "timeout": outcomes["timeout"] / runs,
        "turns": sum(lengths) / runs,
        "minutes": minutes,
        "converted": avg.get("converted", 0),
        "enemies": avg.get("enemies", 0),
        "lost": avg.get("party_size", 0) - avg.get("party_survivors", 0),
        "party": avg.get("party_size", 0),
        "level": avg.get("party_levels", 0) / max(1, avg.get("party_size", 1)),
    }

    print(f"\n=== {node}: {stage['title']} ({runs} battles, player: {policy}) ===")
    print(f"  Outcome        {dict(outcomes)}")
    print(f"  Length         {row['turns']:.0f} unit-turns (min {min(lengths)}, max {max(lengths)}), ~{minutes:.0f} min of real play")
    print(f"  Enemies        {row['enemies']:.0f}: converted {row['converted']:.1f}, fled {avg.get('fled', 0):.1f} (escaped {avg.get('escaped', 0):.1f}), killed {avg.get('kills_by_Player', 0):.1f}, turned back {avg.get('event_@turned_back_hit', 0):.1f}")
    print(f"  Your party     {row['party']:.0f} units, {row['lost']:.1f} lost per battle")
    if preach_tries:
        print(f"  Preach         {preach_tries:.1f} player/enemy attempts, "
              f"{(preach_tries - preach.get('miss', 0)) / preach_tries:.0%} landed; "
              f"converts {preach.get('convert', 0):.1f}, doubt sown {preach.get('shaken', 0):.1f}, despair caused {preach.get('despair', 0):.1f}")
    print(f"  Turns lost     despair {avg.get('turns_lost_despair', 0):.1f}, stun {avg.get('turns_lost_stun', 0):.1f}, "
          f"disarmed (yours) {avg.get('turns_disarmed_Player', 0):.1f}, disarmed (enemy) {avg.get('turns_disarmed_Enemy', 0):.1f}")
    print(f"  Morale surges  {avg.get('morale', 0):.1f} per battle")
    print(f"  Levels         party average Lv {row['level']:.2f} at the end, best Lv {avg.get('best_level', 1):.1f}")
    print(f"  Actions        {actions}")
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", type=int, default=40, help="battles per stage (default 40)")
    parser.add_argument("--stages", default="", help="comma-separated stage ids, e.g. jerusalem,rome (default: all)")
    parser.add_argument("--max-turns", type=int, default=400, help="unit-turns before a battle counts as a timeout")
    parser.add_argument("--player-ai", choices=("human", "game"), default="human",
                        help="who plays your side: a human-like script (default) or the enemy AI")
    args = parser.parse_args(argv)

    pygame.init()
    manifest = load_stage_manifest()
    wanted = [s.strip() for s in args.stages.split(",") if s.strip()] or list(manifest)
    unknown = [s for s in wanted if s not in manifest]
    if unknown:
        parser.error(f"unknown stage(s) {unknown}; choose from {list(manifest)}")

    rows = [simulate_stage(node, manifest[node], args.runs, args.max_turns, args.player_ai) for node in wanted]

    print("\n=== Summary ===")
    print(f"  {'stage':<11}{'win':>6}{'timeout':>9}{'turns':>7}{'~min':>6}{'converted':>11}{'lost':>6}{'avg Lv':>8}")
    for r in rows:
        print(f"  {r['stage']:<11}{r['win']:>6.0%}{r['timeout']:>9.0%}{r['turns']:>7.0f}{r['minutes']:>6.0f}"
              f"{r['converted']:>6.1f}/{r['enemies']:<4.0f}{r['lost']:>6.1f}{r['level']:>8.2f}")


if __name__ == "__main__":
    main()

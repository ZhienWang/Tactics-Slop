"""Regenerates the story stages' battle maps from where each one takes place.

Each stage has a recipe below - Jerusalem's walled streets and temple
platform, Antioch's farms on the Orontes, Philippi's river and Via Egnatia,
Corinth's harbour, Ephesus's theatre, Rome's crowded blocks - built from a
few pieces: rolling ground, roads, rivers and sea, plazas, and props
(houses, wells, ranches, trees, boulders) placed where they make sense.
It writes each stage's map_layout.csv, terrain_layout.csv and props.csv,
your party's start tiles (party_start.csv - as many as the stage had) at
one end, and moves the enemy to the other, never on a prop or in water.
Houses planned as a block (2x2, 3x3, 4x4) stand on levelled ground so the
game draws them as one bigger house.

Damascus (Paul's road to Damascus) is hand-made and left alone.

  - Seeded, so re-running gives the same maps.
  - Every tile that isn't a prop stays reachable on foot (a prop that would
    cut the map in two isn't placed), and no slope is steeper than a
    one-height step, so even a Jump 1 unit can go anywhere.

Run from the project root:   python tools/generate_stage_maps.py [stage ...]
"""
import csv
import io
import math
import os
import random
import sys
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.roster import load_party_slots, save_party_slots  # noqa: E402
STAGES_DIR = os.path.join(ROOT, "data", "stages")

STEP = 0.5          # the steepest slope between two neighbouring tiles
DEFAULT_PARTY_SIZE = 8
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class StageMap:
    def __init__(self, cols, rows, seed, ground):
        self.cols, self.rows = cols, rows
        self.rng = random.Random(seed)
        self.terrain = [[ground] * cols for _ in range(rows)]
        self.height = [[0.0] * cols for _ in range(rows)]
        self.props = {}         # (x, y) -> (kind, height, style)
        self.reserved = set()   # roads, plazas, piers: kept clear of props
        self.fixed = set()      # tiles whose height is set exactly (water, platforms)
        self.blocks = []        # squares of houses to raise as one building

    # --- shape of the ground
    def tiles(self):
        return [(x, y) for y in range(self.rows) for x in range(self.cols)]

    def inside(self, x, y):
        return 0 <= x < self.cols and 0 <= y < self.rows

    def rolling(self, low, high, scale=4.0):
        """Smooth value noise between low and high."""
        gw, gh = int(self.cols / scale) + 2, int(self.rows / scale) + 2
        grid = [[self.rng.random() for _ in range(gw)] for _ in range(gh)]
        for x, y in self.tiles():
            fx, fy = x / scale, y / scale
            ix, iy = int(fx), int(fy)
            tx, ty = fx - ix, fy - iy
            tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
            top = grid[iy][ix] * (1 - tx) + grid[iy][ix + 1] * tx
            bottom = grid[iy + 1][ix] * (1 - tx) + grid[iy + 1][ix + 1] * tx
            self.height[y][x] = low + (high - low) * (top * (1 - ty) + bottom * ty)

    def tilt(self, toward, amount):
        """Raises the ground toward a point, by up to `amount` there."""
        tx, ty = toward
        far = max(math.hypot(tx - x, ty - y) for x, y in self.tiles()) or 1
        for x, y in self.tiles():
            self.height[y][x] += amount * (1 - math.hypot(tx - x, ty - y) / far)

    def set_height(self, tiles, level):
        for x, y in tiles:
            self.height[y][x] = level
            self.fixed.add((x, y))

    def even_out(self, tiles, passes=2):
        """Flattens a road or plaza a little toward its neighbours' average."""
        tiles = list(tiles)
        for _ in range(passes):
            new = {}
            for x, y in tiles:
                around = [self.height[y + dy][x + dx] for dx, dy in NEIGHBOURS + ((0, 0),) if self.inside(x + dx, y + dy)]
                new[(x, y)] = sum(around) / len(around)
            for (x, y), h in new.items():
                if (x, y) not in self.fixed:
                    self.height[y][x] = h

    def settle(self):
        """Rounds heights to half steps and makes every slope walkable:
        no two neighbours more than STEP apart. Fixed tiles keep their
        height; the ground around them gives way."""
        for x, y in self.tiles():
            self.height[y][x] = max(0.0, round(self.height[y][x] * 2) / 2)
        # First lift the ground up to meet any raised platform, then cut it
        # down toward the water and the low ground.
        for pick in (max, min):
            for _ in range(self.cols * self.rows):
                changed = False
                for x, y in self.tiles():
                    if (x, y) in self.fixed:
                        continue
                    h = self.height[y][x]
                    for dx, dy in NEIGHBOURS:
                        if self.inside(x + dx, y + dy):
                            other = self.height[y + dy][x + dx]
                            h = pick(h, other - STEP if pick is max else other + STEP)
                    if h != self.height[y][x]:
                        self.height[y][x], changed = h, True
                if not changed:
                    break

    # --- painting
    def paint(self, tiles, code, reserve=False):
        for x, y in tiles:
            if self.inside(x, y):
                self.terrain[y][x] = code
                if reserve:
                    self.reserved.add((x, y))

    def water(self, tiles):
        tiles = [t for t in tiles if self.inside(*t)]
        self.paint(tiles, "W", reserve=True)
        self.set_height(tiles, 0.0)

    def path(self, points, width=1):
        """Tiles along a 4-connected path through `points`."""
        out = []
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            x, y = ax, ay
            out.append((x, y))
            while (x, y) != (bx, by):
                # Step along whichever axis is further behind the straight line.
                if abs(bx - x) * max(1, abs(by - ay)) >= abs(by - y) * max(1, abs(bx - ax)) and x != bx:
                    x += 1 if bx > x else -1
                else:
                    y += 1 if by > y else -1
                out.append((x, y))
        if width > 1:
            wide = []
            for x, y in out:
                wide += [(x + dx, y + dy) for dx in range(width) for dy in range(width)]
            out = wide
        seen, result = set(), []
        for t in out:
            if t not in seen and self.inside(*t):
                seen.add(t)
                result.append(t)
        return result

    def rect(self, x0, y0, x1, y1):
        return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1) if self.inside(x, y)]

    def is_water(self, x, y):
        return self.terrain[y][x] == "W"

    # --- house blocks
    def plan_block(self, x0, y0, size):
        """Levels a size x size square for a block of houses (call before
        settle); build_blocks puts the houses on it."""
        tiles = self.rect(x0, y0, x0 + size - 1, y0 + size - 1)
        assert len(tiles) == size * size, f"block at {(x0, y0)} runs off the map"
        level = round(sum(self.height[y][x] for x, y in tiles) / len(tiles) * 2) / 2
        self.set_height(tiles, level)
        self.reserved.update(tiles)
        self.blocks.append(tiles)

    def build_blocks(self, height, style):
        for tiles in self.blocks:
            if any(self.is_water(*t) or t in self.props for t in tiles) or not self.connected_without(tiles):
                continue
            for t in tiles:
                self.props[t] = ("house", height, style)

    # --- props
    def connected_without(self, extra):
        """Whether every non-prop tile is still reachable from every other
        with `extra` also blocked."""
        blocked = set(self.props) | set(extra)
        open_tiles = [t for t in self.tiles() if t not in blocked]
        if not open_tiles:
            return False
        seen = {open_tiles[0]}
        queue = deque([open_tiles[0]])
        while queue:
            x, y = queue.popleft()
            for dx, dy in NEIGHBOURS:
                n = (x + dx, y + dy)
                if self.inside(*n) and n not in blocked and n not in seen and abs(self.height[n[1]][n[0]] - self.height[y][x]) <= 1:
                    seen.add(n)
                    queue.append(n)
        return len(seen) == len(open_tiles)

    def place(self, kind, x, y, height, style=""):
        if not self.inside(x, y) or (x, y) in self.props or (x, y) in self.reserved or self.is_water(x, y):
            return False
        if not self.connected_without([(x, y)]):
            return False
        self.props[(x, y)] = (kind, height, style)
        return True

    def scatter(self, kind, count, where, heights, style=""):
        spots = [t for t in self.tiles() if where(*t)]
        self.rng.shuffle(spots)
        placed = 0
        for x, y in spots:
            if placed >= count:
                break
            if self.place(kind, x, y, self.rng.choice(heights), style):
                placed += 1
        return placed

    def beside(self, tiles):
        """Tiles touching any of `tiles` but not among them."""
        tiles = set(tiles)
        out = set()
        for x, y in tiles:
            for dx, dy in NEIGHBOURS:
                n = (x + dx, y + dy)
                if self.inside(*n) and n not in tiles:
                    out.add(n)
        return out

    # --- starting positions
    def start_tiles(self, anchor, count, taken):
        """The `count` dry, open tiles nearest `anchor` on foot."""
        blocked = set(self.props)
        start = min((t for t in self.tiles() if t not in blocked and not self.is_water(*t)),
                    key=lambda t: abs(t[0] - anchor[0]) + abs(t[1] - anchor[1]))
        seen, queue, found = {start}, deque([start]), []
        while queue and len(found) < count:
            x, y = queue.popleft()
            if not self.is_water(x, y) and (x, y) not in taken:
                found.append((x, y))
            for dx, dy in NEIGHBOURS:
                n = (x + dx, y + dy)
                if self.inside(*n) and n not in blocked and n not in seen:
                    seen.add(n)
                    queue.append(n)
        assert len(found) == count, f"only {len(found)} start tiles near {anchor}"
        return found


# --- the stages -------------------------------------------------------------

def jerusalem():
    """The holy city: walled stone streets crossing at a market plaza with a
    well, flat-roofed houses packed along them, a raised temple platform in
    the far corner and a few olive trees in the yards. The apostles gather
    at the near end; the Hellenists who plot against Paul at the temple."""
    m = StageMap(10, 10, seed=301, ground="D")
    m.rolling(0, 1.0)
    m.tilt((9, 9), 1.5)
    temple = m.rect(7, 7, 9, 9)
    streets = m.path([(0, 4), (9, 4)]) + m.path([(4, 0), (4, 9)])
    plaza = m.rect(3, 3, 5, 5)
    m.paint(streets, "C", reserve=True)
    m.paint(plaza, "R", reserve=True)
    m.paint(m.rect(0, 7, 2, 9), "S")                 # the market's sandy yard
    m.paint(temple, "R", reserve=True)
    m.set_height(temple, 1.5)
    m.plan_block(6, 0, 3)                            # a priest's great house
    m.plan_block(0, 5, 2)
    m.even_out(streets + plaza)
    m.settle()
    m.build_blocks(2.5, "flat")
    m.reserved.discard((4, 4))
    m.place("well", 4, 4, 1.5)
    m.reserved.update(m.rect(0, 0, 2, 2))            # where the apostles meet
    lining = [t for t in m.beside(streets + plaza) if t not in temple]
    m.scatter("house", 8, lambda x, y: (x, y) in lining, (2.5, 3), style="flat")
    m.scatter("tree", 3, lambda x, y: m.terrain[y][x] in "DS", (3, 4))
    m.scatter("boulder", 1, lambda x, y: m.terrain[y][x] == "D", (1,))
    return m, (0, 0), (8, 8)


def antioch():
    """Farms on the Orontes: the river along the east edge with mossy banks,
    dirt roads crossing in a small village of flat-roofed houses and a well,
    sheep pens out in the fields and trees on the rise to the west."""
    m = StageMap(11, 11, seed=302, ground="G")
    m.rolling(0.5, 2.0)
    m.tilt((0, 5), 1.0)
    river = []
    for y in range(m.rows):
        edge = 9 - (1 if 3 <= y <= 6 else 0)
        river += [(x, y) for x in range(edge, m.cols)]
    m.water(river)
    roads = m.path([(0, 5), (8, 5)]) + m.path([(4, 0), (4, 10)])
    m.paint(roads, "D", reserve=True)
    for x, y in m.beside(river):
        if m.rng.random() < 0.7:
            m.paint([(x, y)], "M")
    m.paint(m.rect(5, 0, 7, 2), "D")                  # tilled ground
    m.plan_block(1, 3, 2)                            # the farmhouse
    m.even_out(roads)
    m.settle()
    m.build_blocks(2.5, "flat")
    village = [t for t in m.beside(roads) if 2 <= t[0] <= 6 and 3 <= t[1] <= 7]
    m.place("well", 5, 6, 1.5)
    m.scatter("house", 6, lambda x, y: (x, y) in village, (2.5, 3), style="flat")
    for pen in (m.rect(1, 7, 2, 8), m.rect(6, 1, 7, 2), m.rect(6, 8, 7, 8)):
        for x, y in pen:
            m.place("ranch", x, y, 2)
    m.scatter("tree", 6, lambda x, y: m.terrain[y][x] == "G" and x <= 3 and (x, y) not in m.rect(0, 0, 2, 2), (3, 4))
    m.scatter("tree", 2, lambda x, y: m.terrain[y][x] == "M", (3, 4))
    return m, (1, 1), (8, 9)


def philippi():
    """A Roman colony on the Via Egnatia: the paved road crossing the map,
    flat-roofed houses and the stone-yarded jail on the hill above it, and
    the river Gangites below, where Lydia's household meets to pray among
    the trees. Rocks crop out on the high ground."""
    m = StageMap(11, 11, seed=303, ground="G")
    m.rolling(0.5, 1.5)
    m.tilt((10, 0), 1.5)
    river = []
    for x in range(m.cols):
        edge = 9 + (1 if (x // 3) % 2 else 0)
        river += [(x, y) for y in range(edge, m.rows)]
    m.water(river)
    road = m.path([(0, 2), (10, 6)])
    m.paint(road, "C", reserve=True)
    lane = m.path([(5, 5), (5, 8)])
    m.paint(lane, "D", reserve=True)
    jail_yard = m.rect(8, 0, 10, 1)
    m.paint(jail_yard, "R", reserve=True)
    for x, y in m.tiles():
        if m.height[y][x] > 2.4 and m.terrain[y][x] == "G" and m.rng.random() < 0.6:
            m.paint([(x, y)], "R")
    m.plan_block(9, 0, 2)                            # the jail
    m.even_out(road + lane)
    m.settle()
    m.build_blocks(3, "flat")
    m.reserved.update(m.rect(1, 7, 3, 8))            # the place of prayer
    above_road = [t for t in m.beside(road) if t[1] * 10 < t[0] * 4 + 20]  # north of the road
    m.scatter("house", 7, lambda x, y: (x, y) in above_road, (2.5, 3), style="flat")
    m.place("well", 6, 4, 1.5)
    m.scatter("boulder", 4, lambda x, y: m.terrain[y][x] == "R", (1,))
    m.scatter("tree", 5, lambda x, y: m.terrain[y][x] == "G" and y >= 6, (3, 4))
    m.scatter("ranch", 2, lambda x, y: m.terrain[y][x] == "G" and x >= 7 and 6 <= y <= 8, (2,))
    return m, (2, 7), (8, 2)


def corinth():
    """A harbour town on the gulf: the sea along the east with a ragged
    shore and a sandy beach, two wooden quays running out into the water,
    stone streets through a town of flat-roofed houses and wells, and the
    ground climbing west toward the Acrocorinth. Palms line the beach."""
    m = StageMap(11, 12, seed=304, ground="D")
    m.rolling(0, 0.8)
    m.tilt((0, 0), 2.0)
    sea, beach = [], []
    for y in range(m.rows):
        shore = 8 + (1 if y in (0, 1, 10, 11) else 0) - (1 if y in (5, 6) else 0)
        sea += [(x, y) for x in range(shore, m.cols)]
        beach += [(x, y) for x in range(shore - 2, shore)]
    m.water(sea)
    m.paint(beach, "S")
    m.set_height(beach, 0.5)
    for y, length in ((3, 3), (8, 2)):
        shore = min(x for x, yy in sea if yy == y)
        quay = [(x, y) for x in range(shore, min(m.cols, shore + length))]
        m.paint(quay, "P", reserve=True)
        m.set_height(quay, 0.5)
    streets = m.path([(5, 0), (5, 11)]) + m.path([(0, 3), (5, 3)]) + m.path([(0, 8), (5, 8)])
    m.paint(streets, "R", reserve=True)
    m.plan_block(3, 0, 2)                            # warehouses
    m.plan_block(0, 4, 2)
    m.even_out(streets)
    m.settle()
    m.build_blocks(3, "flat")
    lining = [t for t in m.beside(streets) if m.terrain[t[1]][t[0]] == "D"]
    m.reserved.update(m.rect(0, 0, 2, 1))
    m.scatter("house", 12, lambda x, y: (x, y) in lining, (2.5, 3), style="flat")
    m.place("well", 2, 5, 1.5)
    m.place("well", 3, 10, 1.5)
    m.scatter("tree", 4, lambda x, y: m.terrain[y][x] == "S", (3, 4))
    m.scatter("boulder", 2, lambda x, y: m.terrain[y][x] == "D" and x <= 1, (1,))
    return m, (1, 1), (6, 10)


def ephesus():
    """The city below Mount Pion: the marble Curetes Street running down to
    the harbour road, silversmiths' shops along it, and the great theatre in
    the far corner - an orchestra floor with stone tiers rising behind it,
    where the rioting crowd gathers. Grass and trees on the slopes."""
    m = StageMap(12, 12, seed=305, ground="G")
    m.rolling(0.5, 1.5)
    centre = (8.5, 8.5)
    theatre = []
    for x, y in m.tiles():
        d = math.hypot(x - centre[0], y - centre[1])
        if d <= 1.2:
            theatre.append((x, y))
            m.paint([(x, y)], "R", reserve=True)
            m.set_height([(x, y)], 0.5)
        elif d <= 4.2 and x + y >= 17:
            ring = min(4, int(d - 0.2))
            theatre.append((x, y))
            m.paint([(x, y)], "R", reserve=ring % 2 == 0)
            m.set_height([(x, y)], 0.5 + 0.5 * ring)
    street = m.path([(0, 0), (7, 7)], width=1)
    harbour_road = m.path([(0, 6), (6, 6)])
    m.paint(street + harbour_road, "C", reserve=True)
    for x, y in m.tiles():
        if m.terrain[y][x] == "G" and m.rng.random() < 0.15:
            m.paint([(x, y)], "D")
    m.plan_block(1, 7, 2)                            # silversmiths' workshop
    m.plan_block(8, 0, 3)                            # a rich man's house on the hill
    m.even_out(street + harbour_road)
    m.settle()
    m.build_blocks(3, "flat")
    shops = [t for t in m.beside(street + harbour_road) if t not in theatre]
    m.reserved.update(m.rect(0, 0, 2, 2))
    m.scatter("house", 12, lambda x, y: (x, y) in shops, (2.5, 3), style="flat")
    m.place("well", 3, 7, 1.5)
    m.scatter("tree", 7, lambda x, y: m.terrain[y][x] in "GD" and (x, y) not in theatre, (3, 4))
    m.scatter("boulder", 2, lambda x, y: m.terrain[y][x] == "G" and (x, y) not in theatre, (1,))
    return m, (1, 1), (9, 9)


def rome():
    """Nero's Rome: a grid of cobbled streets between crowded blocks of
    flat-roofed houses - an imperial palace filling a whole block, great
    tenements beside it - a paved forum with a fountain, a wooden market,
    a sandy exercise ground and a few garden trees."""
    m = StageMap(12, 12, seed=306, ground="R")
    m.rolling(0, 1.5)
    streets = []
    for y in (1, 6, 11):
        streets += m.path([(0, y), (11, y)])
    for x in (3, 8):
        streets += m.path([(x, 0), (x, 11)])
    m.paint(streets, "C", reserve=True)
    forum = m.rect(4, 7, 7, 10)
    m.paint(forum, "R", reserve=True)
    m.paint(m.rect(9, 7, 11, 10), "P")               # market boards
    m.paint(m.rect(0, 7, 2, 10), "S")                # exercise ground
    m.plan_block(4, 2, 4)                            # the palace
    m.plan_block(0, 2, 3)                            # tenements
    m.plan_block(9, 2, 2)
    m.plan_block(9, 4, 2)
    m.even_out(streets + forum)
    m.settle()
    m.build_blocks(3, "flat")
    m.reserved.discard((5, 8))
    m.place("well", 5, 8, 1.5)
    m.reserved.update(m.rect(0, 0, 2, 0))
    blocks = [t for t in m.tiles() if t not in m.reserved and m.terrain[t[1]][t[0]] == "R"]
    m.scatter("house", 8, lambda x, y: (x, y) in blocks, (2.5, 3), style="flat")
    m.scatter("well", 1, lambda x, y: m.terrain[y][x] == "P", (1.5,))
    m.scatter("tree", 3, lambda x, y: m.terrain[y][x] == "S", (3, 4))
    return m, (1, 0), (10, 11)


RECIPES = {"jerusalem": jerusalem, "antioch": antioch, "philippi": philippi,
           "corinth": corinth, "ephesus": ephesus, "rome": rome}


# --- writing it out ---------------------------------------------------------

def fmt(h):
    return str(int(h)) if float(h).is_integer() else str(h)


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def place_characters(folder, m, player_anchor, enemy_anchor):
    """The party's start tiles (as many as the stage has room for now) near
    `player_anchor`, and the stage's own cast near `enemy_anchor`."""
    path = os.path.join(folder, "characters.csv")
    raw = open(path, encoding="utf-8", newline="").read()
    reader = csv.DictReader(io.StringIO(raw))
    fields, rows = list(reader.fieldnames), list(reader)
    party_size = len(load_party_slots(folder)) or DEFAULT_PARTY_SIZE
    slots = m.start_tiles(player_anchor, party_size, set())
    # The leader (slot 1) takes the tile nearest the anchor that still has
    # open ground beside it - safe at the back of the group, but never boxed
    # into the corner where he can't move on his first turn.
    taken = set(slots)

    def has_room(tile):
        x, y = tile
        return any(m.inside(x + dx, y + dy) and (x + dx, y + dy) not in taken and (x + dx, y + dy) not in m.props
                   and abs(m.height[y + dy][x + dx] - m.height[y][x]) <= 1 for dx, dy in NEIGHBOURS)
    leader = next((t for t in slots if has_room(t)), slots[0])
    slots.remove(leader)
    save_party_slots(folder, [leader] + slots)
    for row, (x, y) in zip(rows, m.start_tiles(enemy_anchor, len(rows), set(slots))):
        row["x"], row["y"] = str(x), str(y)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\r\n" if "\r\n" in raw else "\n")
    writer.writeheader()
    writer.writerows(rows)
    write(path, out.getvalue())


def check(m):
    for x, y in m.tiles():
        for dx, dy in NEIGHBOURS:
            if m.inside(x + dx, y + dy):
                assert abs(m.height[y][x] - m.height[y + dy][x + dx]) <= 1, f"too steep at {(x, y)}"
    assert m.connected_without([]), "the map is cut in two"


def generate(stage_id):
    m, player_anchor, enemy_anchor = RECIPES[stage_id]()
    check(m)
    folder = os.path.join(STAGES_DIR, stage_id)
    write(os.path.join(folder, "map_layout.csv"), "".join(",".join(fmt(h) for h in row) + "\n" for row in m.height))
    write(os.path.join(folder, "terrain_layout.csv"), "".join(",".join(row) + "\n" for row in m.terrain))
    lines = ["x,y,prop,height,style"] + [f"{x},{y},{kind},{fmt(h)},{style}"
                                         for (x, y), (kind, h, style) in sorted(m.props.items(), key=lambda p: (p[0][1], p[0][0]))]
    write(os.path.join(folder, "props.csv"), "\n".join(lines) + "\n")
    place_characters(folder, m, player_anchor, enemy_anchor)
    kinds = {}
    for kind, _, _ in m.props.values():
        kinds[kind] = kinds.get(kind, 0) + 1
    print(f"  {stage_id:10} {m.cols}x{m.rows}  " + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())))


def main(argv):
    stages = argv or list(RECIPES)
    for stage_id in stages:
        if stage_id not in RECIPES:
            sys.exit(f"No recipe for {stage_id!r} (Damascus is hand-made and left alone).")
        generate(stage_id)


if __name__ == "__main__":
    main(sys.argv[1:])

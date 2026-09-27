"""Animated particle effects for skills and items.

Effects are pure data: each row of data/effects.csv picks a motion
`pattern`, a particle `shape`, colors, counts and timings (see
EffectSpec), and can layer other effects on top of itself. Which effect
plays when is bound per skill/item in data/skill_effects.csv (see
data_editor.load_skill_effects_from_csv and game_logic's effect events).

Effects play at a map tile. Every frame the EffectManager is handed a
function turning that tile into a screen point (the tile's center, at the
current rotation/zoom), so an effect stays on its unit while the camera
turns or zooms. All sizes/distances in effects.csv are pixels at zoom 1.

Patterns - how particles move:
  rise      spawn around the feet, drift upward (healing motes)
  fall      spawn overhead, drift down (feathers, blessing rain)
  burst     explode outward from the body, slowing down
  fountain  shoot upward, arc back down under gravity
  spiral    corkscrew up around the unit
  orbit     circle the unit at a fixed height (auras)
  converge  gather inward from a ring to the body (absorb, sap)
  vortex    converge while spinning
  sparkle   twinkle in place around the body
  drip      ooze from the head and trickle down
  miasma    large soft puffs drifting out and up
  ring      ellipses expanding along the ground
  pillar    a column of light plus motes rising in it
  flash     a bright glow swelling and fading (and optional screen flash)
  rays      beams radiating from the body, turning slowly
  glyph     one large symbol that grows, turns and fades
  halo      a ring hovering over the head
"""
import math
import random

import pygame

PATTERNS = (
    "rise", "fall", "burst", "fountain", "spiral", "orbit", "converge", "vortex",
    "sparkle", "drip", "miasma", "ring", "pillar", "flash", "rays", "glyph", "halo",
)
SHAPES = (
    "dot", "glow", "spark", "star", "star5", "cross", "plus", "x", "diamond", "heart",
    "feather", "petal", "leaf", "drop", "bubble", "ring", "bandage", "rune", "eye",
    "shield", "arrow_up", "arrow_down", "net",
)

# How long one particle lives (seconds, random between the two) for the
# patterns that stream particles out: however long the effect runs,
# each particle keeps this snappy lifetime and new ones keep being
# released across the whole effect, so a long effect stays lively rather
# than slowing to a crawl.
PARTICLE_LIFE = {
    "rise": (0.9, 1.5), "fall": (1.1, 1.8), "spiral": (0.9, 1.5), "drip": (1.0, 1.6),
    "miasma": (1.4, 2.2), "converge": (0.8, 1.2), "vortex": (0.8, 1.2), "pillar": (0.9, 1.4),
    "sparkle": (0.35, 0.8),
}
# One-shot patterns repeat in waves of about this many seconds each, so a
# burst/fountain/ring/flash pulses several times over a long effect.
WAVE_PERIOD = {"burst": 0.9, "fountain": 1.1, "ring": 1.0, "flash": 0.8}
# A screen flash always fades within this long, however long its effect.
SCREEN_FLASH_FADE = 0.6

# Where on a unit things happen, in px above the tile center at zoom 1.
BODY_Y = -26
HEAD_Y = -44


def parse_color(text):
    text = text.strip().lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


class EffectSpec:
    """One row of data/effects.csv."""

    def __init__(self, row):
        self.name = row["name"].strip()
        self.category = row.get("category", "").strip()
        self.pattern = row["pattern"].strip()
        self.shape = row.get("shape", "dot").strip() or "dot"
        self.colors = [parse_color(c) for c in row["colors"].split("|") if c.strip()]
        self.count = int(row.get("count") or 0)
        self.duration = int(row.get("duration") or 1000)
        self.speed = float(row.get("speed") or 0)
        self.size = float(row.get("size") or 4)
        self.radius = float(row.get("radius") or 20)
        self.height = float(row.get("height") or 40)
        self.gravity = float(row.get("gravity") or 0)
        self.spin = float(row.get("spin") or 0)
        self.glow = str(row.get("glow", "0")).strip() in ("1", "true", "yes")
        self.screen_flash = int(row.get("screen_flash") or 0)
        self.layers = [n.strip() for n in (row.get("layers") or "").split("|") if n.strip()]
        self.description = row.get("description", "").strip()


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "age", "life", "delay", "size", "color", "angle", "spin",
                 "orbit_angle", "orbit_radius", "orbit_speed", "rise", "seed", "drag", "gravity")

    def __init__(self):
        self.x = self.y = self.vx = self.vy = 0.0
        self.age = 0.0
        self.life = 1.0
        self.delay = 0.0
        self.size = 4.0
        self.color = (255, 255, 255)
        self.angle = 0.0
        self.spin = 0.0
        self.orbit_angle = self.orbit_radius = self.orbit_speed = self.rise = 0.0
        self.seed = 0
        self.drag = 0.0
        self.gravity = 0.0


def _alpha_curve(t):
    """Fade in over the first 15% of a particle's life, out over the last 40%."""
    if t < 0.15:
        return t / 0.15
    if t > 0.6:
        return max(0.0, (1 - t) / 0.4)
    return 1.0


class Effect:
    """A playing instance of an EffectSpec at one map tile."""

    def __init__(self, spec, tile, rng):
        self.spec = spec
        self.tile = tile
        self.rng = rng
        self.age = 0.0
        self.duration = spec.duration / 1000
        self.particles = [self._spawn(i) for i in range(max(1, spec.count))]

    # --- spawning, per pattern ---

    def _spawn(self, index):
        s, rng = self.spec, self.rng
        p = Particle()
        p.color = rng.choice(s.colors) if s.colors else (255, 255, 255)
        p.size = s.size * rng.uniform(0.7, 1.3)
        p.seed = rng.randrange(1 << 30)
        p.angle = rng.uniform(0, 360)
        p.spin = s.spin * rng.uniform(0.6, 1.4) * rng.choice((-1, 1))
        n = max(1, s.count)
        fraction = index / n
        # Most patterns release their particles over the first 60% of the
        # effect, so it builds and trails off rather than popping at once.
        spread = self.duration * 0.6
        p.delay = rng.uniform(0, spread)
        p.life = max(0.15, self.duration - p.delay) * rng.uniform(0.6, 1.0)
        pattern = s.pattern
        angle = rng.uniform(0, math.tau)
        if pattern in PARTICLE_LIFE:
            p.life = min(self.duration, rng.uniform(*PARTICLE_LIFE[pattern]))
            p.delay = rng.uniform(0, max(0.0, self.duration - p.life))
        elif pattern in WAVE_PERIOD:
            period = min(self.duration, WAVE_PERIOD[pattern])
            waves = max(1, int(self.duration / period))
            wave_start = (index % waves) * (self.duration / waves)
            p.delay = wave_start + rng.uniform(0, period * 0.15)
            p.life = max(0.15, min(period * rng.uniform(0.8, 1.05), self.duration - p.delay))

        if pattern == "rise":
            p.x = math.cos(angle) * s.radius * rng.uniform(0.2, 1)
            p.y = math.sin(angle) * s.radius * 0.5 * rng.uniform(0.2, 1)
            p.vy = -s.speed * rng.uniform(0.6, 1.2)
            p.vx = rng.uniform(-0.15, 0.15) * s.speed
        elif pattern == "fall":
            p.x = math.cos(angle) * s.radius * rng.uniform(0, 1)
            p.y = -s.height + math.sin(angle) * s.radius * 0.4
            p.vy = s.speed * rng.uniform(0.6, 1.2)
            p.vx = rng.uniform(-0.2, 0.2) * s.speed
        elif pattern in ("burst", "fountain"):
            p.y = BODY_Y
            if pattern == "burst":
                speed = s.speed * rng.uniform(0.5, 1.1)
                p.vx, p.vy = math.cos(angle) * speed, math.sin(angle) * speed * 0.8
                p.drag = 2.2
            else:
                p.y = 0
                p.vx = rng.uniform(-0.35, 0.35) * s.speed
                p.vy = -s.speed * rng.uniform(0.8, 1.2)
            p.gravity = s.gravity
        elif pattern == "spiral":
            p.orbit_angle = angle
            p.orbit_radius = s.radius * rng.uniform(0.7, 1.1)
            p.orbit_speed = (s.spin or 240) * rng.uniform(0.8, 1.2)
            p.rise = s.speed * rng.uniform(0.8, 1.2)
        elif pattern == "orbit":
            p.delay = fraction * self.duration * 0.2
            p.life = self.duration - p.delay
            p.orbit_angle = fraction * math.tau
            p.orbit_radius = s.radius
            p.orbit_speed = s.spin or 180
            p.y = -s.height
        elif pattern in ("converge", "vortex"):
            p.orbit_angle = angle
            p.orbit_radius = s.radius * rng.uniform(0.8, 1.2)
            p.orbit_speed = (s.spin or 200) if pattern == "vortex" else 0
            p.y = BODY_Y + rng.uniform(-s.height, s.height) * 0.4
        elif pattern == "sparkle":
            p.x = math.cos(angle) * s.radius * rng.uniform(0, 1)
            p.y = BODY_Y + rng.uniform(-s.height, s.height * 0.6)
        elif pattern == "drip":
            p.x = rng.uniform(-s.radius, s.radius)
            p.y = HEAD_Y + rng.uniform(-4, 4)
            p.vy = s.speed * rng.uniform(0.3, 0.7)
            p.gravity = s.gravity or 60
        elif pattern == "miasma":
            p.x = math.cos(angle) * s.radius * 0.3
            p.y = BODY_Y + rng.uniform(-6, 10)
            p.vx = math.cos(angle) * s.speed
            p.vy = -s.speed * rng.uniform(0.3, 0.8)
        elif pattern == "ring":
            pass
        elif pattern == "pillar":
            if index == 0:
                p.delay, p.life = 0, self.duration
            else:
                p.x = rng.uniform(-s.radius, s.radius) * 0.8
                p.y = rng.uniform(-6, 0)
                p.vy = -s.speed * rng.uniform(0.7, 1.3)
        elif pattern == "flash":
            p.y = BODY_Y
        elif pattern == "rays":
            p.delay = 0
            p.life = self.duration
            p.orbit_angle = fraction * math.tau
            p.orbit_speed = s.spin
            p.y = BODY_Y
        elif pattern == "glyph":
            p.delay = fraction * self.duration * 0.25
            p.life = self.duration - p.delay
            p.y = BODY_Y if index == 0 else BODY_Y + rng.uniform(-10, 10)
            p.x = 0 if index == 0 else rng.uniform(-s.radius, s.radius) * 0.5
            p.angle = 0
        elif pattern == "halo":
            p.delay = fraction * self.duration * 0.15
            p.life = self.duration - p.delay
            p.y = HEAD_Y - 8
        return p

    # --- simulation ---

    def update(self, dt):
        self.age += dt
        s = self.spec
        for p in self.particles:
            if self.age < p.delay:
                continue
            p.age += dt
            p.angle += p.spin * dt
            if s.pattern in ("spiral", "orbit", "vortex", "rays"):
                p.orbit_angle += math.radians(p.orbit_speed) * dt
            if s.pattern == "spiral":
                p.y -= p.rise * dt
            if s.pattern in ("converge", "vortex"):
                p.orbit_radius = max(0.0, p.orbit_radius - (self.spec.radius / max(0.1, p.life)) * dt)
            if p.drag:
                p.vx -= p.vx * p.drag * dt
                p.vy -= p.vy * p.drag * dt
            p.vy += p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            if s.pattern in ("rise", "fall", "pillar"):
                p.x += math.sin((p.age * 3) + p.seed % 7) * 8 * dt

    @property
    def finished(self):
        return self.age >= self.duration

    # --- drawing ---

    def screen_flash_alpha(self):
        if not self.spec.screen_flash:
            return 0
        t = self.age / SCREEN_FLASH_FADE
        return round(self.spec.screen_flash * max(0.0, 1 - t))

    def draw(self, layer, glow_target, cx, cy, zoom):
        s = self.spec
        for p in self.particles:
            if self.age < p.delay or p.age >= p.life:
                continue
            t = p.age / p.life
            alpha = _alpha_curve(t)
            if alpha <= 0.01:
                continue
            x, y = p.x, p.y
            if s.pattern in ("spiral", "orbit", "converge", "vortex"):
                x = math.cos(p.orbit_angle) * p.orbit_radius
                y = p.y + math.sin(p.orbit_angle) * p.orbit_radius * 0.45
            px, py = cx + x * zoom, cy + y * zoom
            size = p.size * zoom

            if s.pattern == "ring":
                radius = s.radius * zoom * (0.2 + t * 1.1)
                draw_ellipse_ring(layer, p.color, alpha, px, cy, radius, max(1, round(size * 0.5 * (1 - t) + 1)))
                continue
            if s.pattern == "halo":
                radius = s.radius * zoom * (0.85 + 0.15 * math.sin(p.age * 4))
                draw_ellipse_ring(layer, p.color, alpha, px, py - s.height * zoom * 0.1, radius, max(1, round(size * 0.4)))
                blit_glow(glow_target, p.color, px, py, radius * 1.2, alpha * 0.35)
                continue
            if s.pattern == "pillar" and p is self.particles[0]:
                draw_pillar(layer, p.color, alpha, px, cy, s.radius * zoom, s.height * zoom)
                continue
            if s.pattern == "flash":
                radius = s.radius * zoom * (0.4 + t * 0.9)
                blit_glow(glow_target, p.color, px, py, radius, alpha)
                continue
            if s.pattern == "rays":
                # Rays breathe in and out while they hold.
                length = s.height * zoom * (0.65 + 0.35 * math.sin(p.age * 3 + p.orbit_angle))
                end = (px + math.cos(p.orbit_angle) * length, py + math.sin(p.orbit_angle) * length * 0.7)
                draw_ray(layer, p.color, alpha * 0.8, (px, py), end, max(1, round(size)))
                continue
            if s.pattern == "glyph":
                # Grow in, then pulse gently while held.
                grow = (0.6 + 0.4 * min(1.0, t * 3)) * (1 + 0.07 * math.sin(p.age * 4))
                if p is self.particles[0]:
                    size = s.size * zoom * grow
                    if s.glow:
                        blit_glow(glow_target, p.color, px, py, size * 1.4, alpha * 0.5)
                elif s.glow:
                    blit_glow(glow_target, p.color, px, py, size * 1.6, alpha * 0.6)
            if s.pattern == "sparkle":
                size *= 0.6 + 0.6 * math.sin(t * math.pi)
            if s.glow and s.pattern != "glyph":
                blit_glow(glow_target, p.color, px, py, size * 2.2, alpha * 0.55)
            draw_shape(layer, s.shape, p, px, py, size, alpha)


# --- drawing helpers -------------------------------------------------------------

def _rgba(color, alpha):
    return (*color[:3], max(0, min(255, round(255 * alpha))))


def _rotated(points, angle, px, py, size):
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return [(px + (x * ca - y * sa) * size, py + (x * sa + y * ca) * size) for x, y in points]


# Unit-size outlines (radius ~1) for the polygon shapes.
_STAR4 = [(0, -1), (0.25, -0.25), (1, 0), (0.25, 0.25), (0, 1), (-0.25, 0.25), (-1, 0), (-0.25, -0.25)]
_STAR5 = [(math.cos(math.radians(-90 + i * 36)) * (1 if i % 2 == 0 else 0.42),
           math.sin(math.radians(-90 + i * 36)) * (1 if i % 2 == 0 else 0.42)) for i in range(10)]
_CROSS = [(-0.18, -1), (0.18, -1), (0.18, -0.45), (0.6, -0.45), (0.6, -0.12), (0.18, -0.12),
          (0.18, 1), (-0.18, 1), (-0.18, -0.12), (-0.6, -0.12), (-0.6, -0.45), (-0.18, -0.45)]
_PLUS = [(-0.3, -1), (0.3, -1), (0.3, -0.3), (1, -0.3), (1, 0.3), (0.3, 0.3), (0.3, 1), (-0.3, 1),
         (-0.3, 0.3), (-1, 0.3), (-1, -0.3), (-0.3, -0.3)]
_X = [(x * 0.707 - y * 0.707, x * 0.707 + y * 0.707) for x, y in _PLUS]
_DIAMOND = [(0, -1), (0.6, 0), (0, 1), (-0.6, 0)]
_HEART = [(0, 1)] + [(math.sin(a) ** 3, -(13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)) / 16)
                     for a in [i * math.tau / 24 for i in range(1, 24)]]
_PETAL = [(0, -1), (0.45, -0.3), (0.35, 0.5), (0, 1), (-0.35, 0.5), (-0.45, -0.3)]
_LEAF = [(0, -1), (0.4, -0.4), (0.35, 0.4), (0, 1), (-0.35, 0.4), (-0.4, -0.4)]
_FEATHER = [(0, -1), (0.28, -0.6), (0.3, 0.2), (0.1, 0.8), (0, 1), (-0.1, 0.8), (-0.3, 0.2), (-0.28, -0.6)]
# A teardrop: point on top, round belly below (screen y grows downward).
_DROP = [(0, -1)] + [(0.55 * math.cos(t), 0.35 + 0.55 * math.sin(t))
                     for t in [-0.6 + i * (math.pi + 1.2) / 12 for i in range(13)]]
_SHIELD = [(-0.8, -0.9), (0.8, -0.9), (0.8, 0.1), (0, 1), (-0.8, 0.1)]
_ARROW_UP = [(0, -1), (0.8, -0.1), (0.3, -0.1), (0.3, 1), (-0.3, 1), (-0.3, -0.1), (-0.8, -0.1)]
_ARROW_DOWN = [(x, -y) for x, y in _ARROW_UP]

POLYGONS = {
    "star": _STAR4, "star5": _STAR5, "cross": _CROSS, "plus": _PLUS, "x": _X, "diamond": _DIAMOND,
    "heart": _HEART, "petal": _PETAL, "leaf": _LEAF, "feather": _FEATHER, "drop": _DROP,
    "shield": _SHIELD, "arrow_up": _ARROW_UP, "arrow_down": _ARROW_DOWN,
}
# Shapes that stay upright instead of spinning (symbols read wrong tilted).
UPRIGHT = {"cross", "plus", "heart", "drop", "shield", "arrow_up", "arrow_down", "eye", "bandage"}


def draw_shape(layer, shape, p, px, py, size, alpha):
    color = _rgba(p.color, alpha)
    if size < 0.6:
        return
    if shape in POLYGONS:
        angle = 0 if shape in UPRIGHT else p.angle
        points = _rotated(POLYGONS[shape], angle, px, py, size)
        pygame.draw.polygon(layer, color, points)
        if shape == "feather":
            spine = _rotated([(0, -0.9), (0, 1.2)], angle, px, py, size)
            pygame.draw.line(layer, _rgba((200, 200, 210), alpha), spine[0], spine[1], 1)
        elif shape == "leaf":
            spine = _rotated([(0, -0.8), (0, 0.9)], angle, px, py, size)
            pygame.draw.line(layer, _rgba(tuple(c // 2 for c in p.color), alpha), spine[0], spine[1], 1)
        elif shape == "shield":
            inner = _rotated([(0, -0.55), (0, 0.55)], 0, px, py, size)
            pygame.draw.line(layer, _rgba((255, 255, 255), alpha * 0.8), inner[0], inner[1], max(1, round(size * 0.2)))
        return
    if shape == "dot":
        pygame.draw.circle(layer, color, (round(px), round(py)), max(1, round(size * 0.5)))
    elif shape == "glow":
        pygame.draw.circle(layer, _rgba(p.color, alpha * 0.5), (round(px), round(py)), max(1, round(size)))
        pygame.draw.circle(layer, color, (round(px), round(py)), max(1, round(size * 0.45)))
    elif shape == "spark":
        speed = math.hypot(p.vx, p.vy) or 1
        dx, dy = (p.vx / speed, p.vy / speed) if (p.vx or p.vy) else (math.cos(math.radians(p.angle)), math.sin(math.radians(p.angle)))
        length = size * 2.2
        pygame.draw.line(layer, color, (px - dx * length, py - dy * length), (px, py), max(1, round(size * 0.35)))
    elif shape in ("bubble", "ring"):
        pygame.draw.circle(layer, color, (round(px), round(py)), max(2, round(size)), max(1, round(size * 0.22)))
        if shape == "bubble":
            pygame.draw.circle(layer, _rgba((255, 255, 255), alpha), (round(px - size * 0.35), round(py - size * 0.35)), max(1, round(size * 0.22)))
    elif shape == "bandage":
        body = _rotated([(-1, -0.35), (1, -0.35), (1, 0.35), (-1, 0.35)], p.angle * 0.2, px, py, size)
        pygame.draw.polygon(layer, _rgba((250, 246, 236), alpha), body)
        mark = _rotated(_PLUS, 0, px, py, size * 0.28)
        pygame.draw.polygon(layer, _rgba(p.color, alpha), mark)
    elif shape == "rune":
        rng = random.Random(p.seed)
        points = [(px + rng.uniform(-1, 1) * size, py + rng.uniform(-1, 1) * size) for _ in range(4)]
        pygame.draw.lines(layer, color, False, points, max(1, round(size * 0.18)))
    elif shape == "eye":
        rect = pygame.Rect(0, 0, round(size * 2.4), round(size * 1.2))
        rect.center = (round(px), round(py))
        pygame.draw.ellipse(layer, color, rect, max(1, round(size * 0.18)))
        pygame.draw.circle(layer, color, rect.center, max(1, round(size * 0.4)))
    elif shape == "net":
        for i in range(-2, 3):
            a = _rotated([(i * 0.4, -1), (i * 0.4, 1)], 45, px, py, size)
            b = _rotated([(-1, i * 0.4), (1, i * 0.4)], 45, px, py, size)
            pygame.draw.line(layer, color, a[0], a[1], 1)
            pygame.draw.line(layer, color, b[0], b[1], 1)


def draw_ellipse_ring(layer, color, alpha, cx, cy, radius, width):
    if radius < 2:
        return
    rect = pygame.Rect(0, 0, round(radius * 2), max(2, round(radius * 0.9)))
    rect.center = (round(cx), round(cy))
    pygame.draw.ellipse(layer, _rgba(color, alpha), rect, width)


def draw_pillar(layer, color, alpha, cx, base_y, radius, height):
    """A soft vertical beam: stacked translucent bands, brightest at the core."""
    for fraction, strength in ((1.0, 0.25), (0.6, 0.4), (0.25, 0.7)):
        width = max(2, round(radius * 2 * fraction))
        rect = pygame.Rect(0, 0, width, round(height))
        rect.midbottom = (round(cx), round(base_y))
        pygame.draw.rect(layer, _rgba(color, alpha * strength), rect, border_radius=width // 2)


def draw_ray(layer, color, alpha, start, end, width):
    pygame.draw.line(layer, _rgba(color, alpha), start, end, width)


_glow_cache = {}


def _glow_sprite(color, radius, level):
    """A radial glow, premultiplied by its alpha level (0..16) so it can be
    added onto the screen - light adds up rather than covering."""
    key = (color, radius, level)
    sprite = _glow_cache.get(key)
    if sprite is None:
        if len(_glow_cache) > 3000:
            _glow_cache.clear()
        sprite = pygame.Surface((radius * 2, radius * 2))
        steps = max(4, min(12, radius // 2))
        for i in range(steps, 0, -1):
            r = radius * i / steps
            strength = (1 - i / steps) ** 1.5 * level / 16
            pygame.draw.circle(sprite, tuple(round(c * strength) for c in color), (radius, radius), max(1, round(r)))
        _glow_cache[key] = sprite
    return sprite


def blit_glow(target, color, x, y, radius, alpha):
    radius = max(2, round(radius))
    level = max(0, min(16, round(alpha * 16)))
    if level == 0 or target is None:
        return
    sprite = _glow_sprite(tuple(color[:3]), radius, level)
    target.blit(sprite, (round(x - radius), round(y - radius)), special_flags=pygame.BLEND_RGB_ADD)


class EffectManager:
    """Plays effects over the battlefield. `specs` is {name: EffectSpec}."""

    def __init__(self, specs, seed=None):
        self.specs = specs
        self.effects = []
        self.rng = random.Random(seed)
        self.last_ticks = None
        self.layer = None

    def play(self, name, tile):
        spec = self.specs.get(name)
        if spec is None:
            return
        if spec.count > 0 or not spec.layers:
            self.effects.append(Effect(spec, tile, self.rng))
        for layer_name in spec.layers:
            if layer_name != name:
                self.play(layer_name, tile)

    @property
    def active(self):
        return bool(self.effects)

    def draw(self, surface, tile_to_screen, zoom=1.0, now=None):
        """Advance and draw every playing effect. tile_to_screen(tile) gives
        the screen point of that tile's center."""
        now = pygame.time.get_ticks() if now is None else now
        dt = 0.0 if self.last_ticks is None else min(0.1, (now - self.last_ticks) / 1000)
        self.last_ticks = now
        if not self.effects:
            return
        if self.layer is None or self.layer.get_size() != surface.get_size():
            self.layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        self.layer.fill((0, 0, 0, 0))
        flash = 0
        flash_color = (255, 255, 255)
        for effect in self.effects:
            effect.update(dt)
            cx, cy = tile_to_screen(effect.tile)
            effect.draw(self.layer, surface, cx, cy, zoom)
            alpha = effect.screen_flash_alpha()
            if alpha > flash:
                flash, flash_color = alpha, effect.spec.colors[0] if effect.spec.colors else (255, 255, 255)
        surface.blit(self.layer, (0, 0))
        if flash:
            overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            overlay.fill((*flash_color, flash))
            surface.blit(overlay, (0, 0))
        self.effects = [e for e in self.effects if not e.finished]

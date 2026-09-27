"""Battle weather: a screen-space effect drawn over the map and units but
under the HUD. Each stage picks its weather in data/stages/<stage>/weather.csv
(see data_editor.load_weather_from_csv).

- sunny:      warm light and slow, soft sunbeams
- rain:       steady rain, a slightly grey sky
- heavy_rain: dense, fast, wind-slanted rain and a darker sky
- storm:      heavy rain, a dark sky and lightning strikes
"""
import math
import random

import pygame

WEATHER_TYPES = ("sunny", "rain", "heavy_rain", "storm")
DEFAULT_WEATHER = "sunny"

# Per weather type: how many drops are falling at once, their fall speed
# (px/s), how far the wind pushes them sideways per pixel fallen, streak
# length and thickness, and the RGBA sky tint laid over the whole battlefield.
RAIN_PROFILES = {
    "rain": {"drops": 260, "speed": (650, 850), "wind": 0.12, "length": (12, 18), "width": 1, "color": (190, 210, 240, 170), "tint": (40, 55, 80, 50)},
    "heavy_rain": {"drops": 520, "speed": (950, 1250), "wind": 0.25, "length": (18, 28), "width": 2, "color": (195, 212, 240, 150), "tint": (25, 35, 60, 85)},
    "storm": {"drops": 650, "speed": (1100, 1450), "wind": 0.38, "length": (20, 32), "width": 2, "color": (200, 215, 245, 160), "tint": (10, 15, 35, 115)},
}
SPLASH_MS = 180
# Storm lightning: seconds between strikes, and how long a flash lasts.
LIGHTNING_GAP = (3.5, 8.0)
LIGHTNING_FLASH_MS = 260
LIGHTNING_BOLT_MS = 140


class Weather:
    def __init__(self, kind, width, height, seed=None):
        self.kind = kind if kind in WEATHER_TYPES else DEFAULT_WEATHER
        self.width, self.height = width, height
        self.rng = random.Random(seed)
        self.layer = pygame.Surface((width, height), pygame.SRCALPHA)
        self.last_ticks = None
        self.profile = RAIN_PROFILES.get(self.kind)
        self.drops = [self._new_drop(initial=True) for _ in range(self.profile["drops"])] if self.profile else []
        self.splashes = []
        self.tint = None
        if self.profile:
            self.tint = pygame.Surface((width, height), pygame.SRCALPHA)
            self.tint.fill(self.profile["tint"])
        self.sunbeams = self._build_sunbeams() if self.kind == "sunny" else None
        self.next_strike = self._strike_delay() if self.kind == "storm" else None
        self.flash_started = None
        self.bolt = None

    # --- rain ---

    def _new_drop(self, initial=False):
        low, high = self.profile["speed"]
        length_low, length_high = self.profile["length"]
        # Drops start above the screen (or anywhere on it, for the first
        # frame, so the rain doesn't visibly "arrive") and are shifted left
        # to make up for the wind carrying them right as they fall.
        drift = self.profile["wind"] * self.height
        return {
            "x": self.rng.uniform(-drift, self.width),
            "y": self.rng.uniform(-self.height, self.height) if initial else self.rng.uniform(-60, -10),
            "speed": self.rng.uniform(low, high),
            "length": self.rng.uniform(length_low, length_high),
            # Where this drop hits the ground - somewhere down the screen,
            # not all at the bottom edge, since the map is seen from above.
            "land_y": self.rng.uniform(self.height * 0.25, self.height),
        }

    def _update_rain(self, dt, now):
        wind = self.profile["wind"]
        for index, drop in enumerate(self.drops):
            fall = drop["speed"] * dt
            drop["y"] += fall
            drop["x"] += fall * wind
            if drop["y"] >= drop["land_y"]:
                self.splashes.append((drop["x"], drop["land_y"], now))
                self.drops[index] = self._new_drop()
        self.splashes = [s for s in self.splashes if now - s[2] < SPLASH_MS]

    def _draw_rain(self, now):
        color = self.profile["color"]
        wind = self.profile["wind"]
        width = self.profile["width"]
        for drop in self.drops:
            tail_x = drop["x"] - drop["length"] * wind
            tail_y = drop["y"] - drop["length"]
            pygame.draw.line(self.layer, color, (tail_x, tail_y), (drop["x"], drop["y"]), width)
        for x, y, start in self.splashes:
            progress = (now - start) / SPLASH_MS
            radius = 2 + 5 * progress
            alpha = round(color[3] * (1 - progress))
            rect = pygame.Rect(0, 0, round(radius * 2), max(1, round(radius * 0.8)))
            rect.center = (round(x), round(y))
            pygame.draw.ellipse(self.layer, (*color[:3], alpha), rect, 1)

    # --- storm ---

    def _strike_delay(self):
        return self.rng.uniform(*LIGHTNING_GAP)

    def _new_bolt(self):
        x = self.rng.uniform(self.width * 0.2, self.width * 0.8)
        y = 0.0
        points = [(x, y)]
        ground = self.rng.uniform(self.height * 0.35, self.height * 0.7)
        while y < ground:
            y += self.rng.uniform(25, 55)
            x += self.rng.uniform(-35, 35)
            points.append((x, min(y, ground)))
        return points

    def _update_storm(self, dt, now):
        self.next_strike -= dt
        if self.next_strike <= 0:
            self.flash_started = now
            self.bolt = self._new_bolt()
            self.next_strike = self._strike_delay()

    def _draw_storm(self, surface, now):
        if self.flash_started is None:
            return
        elapsed = now - self.flash_started
        if elapsed >= LIGHTNING_FLASH_MS:
            self.flash_started = None
            return
        if self.bolt and elapsed < LIGHTNING_BOLT_MS:
            pygame.draw.lines(self.layer, (190, 200, 255, 160), False, self.bolt, 6)
            pygame.draw.lines(self.layer, (255, 255, 255, 255), False, self.bolt, 2)
        # A double flicker: bright, a quick dip, a second smaller flash.
        progress = elapsed / LIGHTNING_FLASH_MS
        strength = (1 - progress) * (0.55 if 0.25 < progress < 0.4 else 1.0)
        flash = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        flash.fill((225, 230, 255, round(150 * strength)))
        surface.blit(flash, (0, 0))

    # --- sun ---

    def _build_sunbeams(self):
        beams = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        beams.fill((255, 214, 140, 22))
        # Broad diagonal shafts of light from the upper left, matching the
        # map lighting's sun direction.
        for offset, width, alpha in ((-200, 140, 22), (120, 90, 18), (380, 170, 16), (720, 110, 14)):
            top_left = offset
            polygon = [(top_left, 0), (top_left + width, 0),
                       (top_left + width + self.height * 0.8, self.height), (top_left + self.height * 0.8, self.height)]
            pygame.draw.polygon(beams, (255, 236, 180, alpha), polygon)
        return beams

    def _draw_sun(self, surface, now):
        # The beams breathe slowly so the light feels alive.
        self.sunbeams.set_alpha(round(200 + 55 * math.sin(now / 1800)))
        surface.blit(self.sunbeams, (0, 0))

    # --- frame ---

    def draw(self, surface):
        now = pygame.time.get_ticks()
        dt = 0.0 if self.last_ticks is None else min(0.1, (now - self.last_ticks) / 1000)
        self.last_ticks = now

        if self.kind == "sunny":
            self._draw_sun(surface, now)
            return

        self._update_rain(dt, now)
        if self.kind == "storm":
            self._update_storm(dt, now)
        surface.blit(self.tint, (0, 0))
        self.layer.fill((0, 0, 0, 0))
        self._draw_rain(now)
        if self.kind == "storm":
            self._draw_storm(surface, now)
        surface.blit(self.layer, (0, 0))

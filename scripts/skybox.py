"""Battle skybox: a procedural panorama drawn behind the map in place of a
flat background picture.

It is built once per battle from the stage's weather (see weather.py) -
a sky gradient, a sun, two ridges of distant hills and drifting clouds.
The panorama wraps around horizontally, so rotating the map (Q/E) swings
the view a quarter of the way round, and panning the camera slides the
layers at different speeds for a little parallax depth.
"""
import math
import random

import pygame

# Per weather type: sky colour at the top of the screen, at the horizon, the
# haze below the horizon (under the map), the two hill ridges (far, near),
# how many clouds there are and their colour, and whether the sun shows.
SKY_PROFILES = {
    "sunny": {"top": (58, 108, 178), "horizon": (196, 214, 226), "ground": (52, 60, 66),
              "far": (124, 146, 170), "near": (86, 104, 110), "clouds": 9, "cloud": (250, 250, 252, 170), "sun": True},
    "rain": {"top": (62, 74, 92), "horizon": (138, 148, 158), "ground": (40, 44, 50),
             "far": (100, 110, 122), "near": (70, 78, 86), "clouds": 16, "cloud": (170, 176, 186, 190), "sun": False},
    "heavy_rain": {"top": (40, 48, 62), "horizon": (104, 112, 122), "ground": (30, 34, 40),
                   "far": (78, 86, 98), "near": (54, 60, 68), "clouds": 22, "cloud": (120, 126, 138, 205), "sun": False},
    "storm": {"top": (16, 20, 32), "horizon": (64, 68, 84), "ground": (18, 20, 26),
              "far": (50, 54, 70), "near": (34, 38, 48), "clouds": 26, "cloud": (70, 74, 92, 215), "sun": False},
}
DEFAULT_SKY = "sunny"

# Where the horizon sits, as a fraction of the screen height.
HORIZON = 0.46
# How far each layer moves per pixel the camera pans (0 = fixed to the sky).
FAR_PARALLAX = 0.08
NEAR_PARALLAX = 0.18
CLOUD_PARALLAX = 0.04
# Seconds for the view to swing round after a map rotation.
ROTATE_EASE = 0.35
# Cloud drift speed range, in panorama pixels per second.
CLOUD_DRIFT = (6, 16)


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


class Skybox:
    def __init__(self, kind, width, height, seed=None):
        self.profile = SKY_PROFILES.get(kind, SKY_PROFILES[DEFAULT_SKY])
        self.width, self.height = width, height
        # The panorama is two screens wide; each map rotation is a quarter of it.
        self.pano_width = width * 2
        self.horizon_y = round(height * HORIZON)
        self.rng = random.Random(seed)
        # The hill layers span from well above the horizon (room for the
        # tallest peaks and the sun) to below the screen bottom, since they're
        # blitted with a vertical parallax offset.
        self.layer_top = self.horizon_y - 320

        self.gradient = self._build_gradient()
        self.sun = self._build_sun() if self.profile["sun"] else None
        self.far_layer = self._build_ridge(self.profile["far"], amplitude=150, base=18, detail=6)
        self.near_layer = self._build_ridge(self.profile["near"], amplitude=85, base=-6, detail=9)
        self.cloud_sprites = [self._build_cloud() for _ in range(5)]
        self.clouds = [self._new_cloud() for _ in range(self.profile["clouds"])]

        self.view = None
        self.last_ticks = None
        self.sun_pos = None

    # --- building ---

    def _build_gradient(self):
        surface = pygame.Surface((self.width, self.height))
        top, horizon, ground = self.profile["top"], self.profile["horizon"], self.profile["ground"]
        for y in range(self.height):
            if y <= self.horizon_y:
                # Ease towards the horizon so the pale band stays thin.
                t = (y / self.horizon_y) ** 1.6
                color = _lerp(top, horizon, t)
            else:
                t = min(1.0, (y - self.horizon_y) / (self.height - self.horizon_y) * 1.8)
                color = _lerp(horizon, ground, t ** 0.7)
            pygame.draw.line(surface, color, (0, y), (self.width, y))
        return surface

    def _ridge_heights(self, amplitude, detail):
        # A sum of sines at whole-number frequencies of the panorama width, so
        # the ridge line joins up seamlessly where the panorama wraps.
        waves = [(self.rng.randint(2, 4) * (i + 1), self.rng.uniform(0, math.tau), amplitude / (i + 1) ** 1.1)
                 for i in range(detail)]
        total = sum(w[2] for w in waves)
        heights = []
        for x in range(self.pano_width + 1):
            angle = x / self.pano_width * math.tau
            value = sum(amp * math.sin(freq * angle + phase) for freq, phase, amp in waves)
            heights.append(amplitude * (0.55 + 0.45 * value / total))
        return heights

    def _build_ridge(self, color, amplitude, base, detail):
        layer = pygame.Surface((self.pano_width, self.height - self.layer_top + 120), pygame.SRCALPHA)
        horizon = self.horizon_y - self.layer_top
        heights = self._ridge_heights(amplitude, detail)
        ground = self.profile["ground"]
        points = [(x, horizon + base - heights[x]) for x in range(0, self.pano_width + 1, 4)]
        points += [(self.pano_width, layer.get_height()), (0, layer.get_height())]
        pygame.draw.polygon(layer, color, points)
        # Fade the ridge into the ground haze below, so the hills sit in mist
        # rather than ending in a hard edge under the map.
        fade_top = horizon + base
        for y in range(round(fade_top), layer.get_height()):
            t = min(1.0, (y - fade_top) / 220)
            pygame.draw.line(layer, (*_lerp(color, ground, t), 255), (0, y), (self.pano_width, y))
        return layer

    def _build_sun(self):
        glow = pygame.Surface((520, 520), pygame.SRCALPHA)
        for radius in range(260, 40, -6):
            alpha = round(38 * (1 - radius / 260) ** 1.5)
            pygame.draw.circle(glow, (255, 236, 190, alpha), (260, 260), radius)
        pygame.draw.circle(glow, (255, 248, 222, 255), (260, 260), 38)
        return glow

    def _build_cloud(self):
        width, height = self.rng.randint(160, 320), self.rng.randint(50, 90)
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        r, g, b, a = self.profile["cloud"]
        # A flat-bottomed heap of puffs, shaded slightly darker underneath.
        for _ in range(self.rng.randint(6, 10)):
            pw = self.rng.randint(width // 4, width // 2)
            ph = self.rng.randint(height // 2, height)
            px = self.rng.randint(0, width - pw)
            py = self.rng.randint(0, height - ph)
            shade = 0.85 + 0.15 * (1 - (py + ph / 2) / height)
            pygame.draw.ellipse(surface, (round(r * shade), round(g * shade), round(b * shade), a // 3), (px, py, pw, ph))
        return surface

    def _new_cloud(self):
        sprite = self.rng.choice(self.cloud_sprites)
        scale = self.rng.uniform(0.7, 1.4)
        size = (round(sprite.get_width() * scale), round(sprite.get_height() * scale))
        return {
            "sprite": pygame.transform.smoothscale(sprite, size),
            "x": self.rng.uniform(0, self.pano_width),
            "y": self.rng.uniform(self.horizon_y * 0.05, self.horizon_y * 0.75),
            "speed": self.rng.uniform(*CLOUD_DRIFT),
        }

    # --- frame ---

    def _blit_wrapped(self, surface, layer, x_offset, y):
        x = -(x_offset % self.pano_width)
        surface.blit(layer, (x, y))
        if x + self.pano_width < self.width:
            surface.blit(layer, (x + self.pano_width, y))

    def draw(self, surface, rotation, pan_x, pan_y):
        now = pygame.time.get_ticks()
        dt = 0.0 if self.last_ticks is None else min(0.1, (now - self.last_ticks) / 1000)
        self.last_ticks = now

        # Ease the view angle towards the current rotation along the shorter
        # way round, so Q/E swings the sky instead of snapping it.
        target = rotation * self.pano_width / 4
        if self.view is None:
            self.view = target
        else:
            delta = (target - self.view + self.pano_width / 2) % self.pano_width - self.pano_width / 2
            self.view += delta * min(1.0, dt / ROTATE_EASE * 3)
        view = self.view

        surface.blit(self.gradient, (0, 0))

        # Where the sun is on screen this frame (None when it's off screen or
        # the sky has none) - for light that should come from it.
        self.sun_pos = None
        if self.sun:
            # Upper left of the opening view (rotation 2), matching the map
            # lighting's sun direction; it sits behind everything else.
            sun_x = (self.pano_width / 2 + self.width * 0.3 - view - pan_x * CLOUD_PARALLAX) % self.pano_width
            sun_y = self.horizon_y * 0.35 + pan_y * CLOUD_PARALLAX
            for x in (sun_x, sun_x - self.pano_width):
                surface.blit(self.sun, (x - 260, sun_y - 260))
                if 0 <= x <= self.width:
                    self.sun_pos = (x, sun_y)

        for cloud in self.clouds:
            cloud["x"] = (cloud["x"] + cloud["speed"] * dt) % self.pano_width
            sprite = cloud["sprite"]
            x = (cloud["x"] - view - pan_x * CLOUD_PARALLAX) % self.pano_width
            y = cloud["y"] + pan_y * CLOUD_PARALLAX
            surface.blit(sprite, (x, y))
            # Clouds straddling the wrap point also show on the other side.
            if x + sprite.get_width() > self.pano_width:
                surface.blit(sprite, (x - self.pano_width, y))

        self._blit_wrapped(surface, self.far_layer, view - pan_x * FAR_PARALLAX, self.layer_top + pan_y * FAR_PARALLAX)
        self._blit_wrapped(surface, self.near_layer, view - pan_x * NEAR_PARALLAX, self.layer_top + pan_y * NEAR_PARALLAX)

import os
import sys
import pygame
from scripts.config import SCREEN_WIDTH, SCREEN_HEIGHT, TILE_WIDTH, TILE_HEIGHT


def bring_window_to_front():
    """Force the game window to the foreground so it doesn't open behind other windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = pygame.display.get_wm_info().get("window")
        if hwnd:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def load_image_safe(path, invalid_paths=None):
    if not path:
        return None
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), path)
    if not os.path.exists(path):
        if invalid_paths is not None:
            invalid_paths.append((path, "missing file"))
        return None
    try:
        return pygame.image.load(path).convert_alpha()
    except Exception as exc:
        if invalid_paths is not None:
            invalid_paths.append((path, f"load failed ({exc})"))
        return None


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


def load_background_image(background_path, invalid_assets):
    if not background_path:
        return None
    img = load_image_safe(background_path, invalid_assets)
    if img:
        scale = min(SCREEN_WIDTH / img.get_width(), SCREEN_HEIGHT / img.get_height())
        scaled_size = (round(img.get_width() * scale), round(img.get_height() * scale))
        scaled_image = pygame.transform.smoothscale(img, scaled_size)
        background = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        background.fill((0, 0, 0))
        background.blit(scaled_image, scaled_image.get_rect(center=background.get_rect().center))
        return background
    return None


def create_projectile_surface(color, size=16):
    surf = pygame.Surface((size, size // 2), pygame.SRCALPHA)
    body_color = color
    tip_color = tuple(max(0, min(255, c + 70)) for c in color)
    pygame.draw.rect(surf, body_color, (0, size // 4 - 1, size - 6, 3))
    pygame.draw.polygon(surf, tip_color, [(size - 6, 0), (size - 1, size // 4), (size - 6, size // 2)])
    pygame.draw.rect(surf, (0, 0, 0), (0, size // 4 - 1, size - 6, 3), 1)
    pygame.draw.polygon(surf, (0, 0, 0), [(size - 6, 0), (size - 1, size // 4), (size - 6, size // 2)], 1)
    return surf


def cache_terrain_images(terrain_layout, invalid_assets):
    terrain_image_cache = {}
    for row in terrain_layout:
        for path in row:
            if path and path not in terrain_image_cache:
                terrain_image_cache[path] = load_image_safe(path, invalid_assets)
    return terrain_image_cache


def average_tile_color(image):
    """Cheap average color of a texture (downscale to 1x1), used so a
    tile's cube side-walls shade toward its own texture's color instead of
    a generic grey."""
    tiny = pygame.transform.smoothscale(image, (1, 1))
    return tiny.get_at((0, 0))[:3]


def cache_terrain_colors(terrain_image_cache):
    return {
        path: average_tile_color(image)
        for path, image in terrain_image_cache.items()
        if image
    }


def build_character_portraits(units, invalid_assets):
    portraits = {}
    for u in units:
        portrait_img = load_image_safe(u.portrait_path, invalid_assets)
        if portrait_img:
            if u.name == "Centurion Marcus":
                gold_tint = pygame.Surface(portrait_img.get_size(), pygame.SRCALPHA)
                gold_tint.fill((255, 190, 40, 255))
                portrait_img = portrait_img.copy()
                portrait_img.blit(gold_tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            portraits[u.name] = pygame.transform.smoothscale(portrait_img, (140, 70))
        else:
            portraits[u.name] = create_portrait_surface(u.color, u.name)
    return portraits

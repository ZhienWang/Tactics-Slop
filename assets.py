import os
import pygame
from config import SCREEN_WIDTH, SCREEN_HEIGHT, TILE_WIDTH, TILE_HEIGHT


def load_image_safe(path, invalid_paths=None):
    if not path:
        return None
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
        return pygame.transform.smoothscale(img, (SCREEN_WIDTH, SCREEN_HEIGHT))
    return None


def cache_terrain_images(terrain_layout, invalid_assets):
    terrain_image_cache = {}
    for row in terrain_layout:
        for path in row:
            if path and path not in terrain_image_cache:
                terrain_image_cache[path] = load_image_safe(path, invalid_assets)
    return terrain_image_cache


def build_character_portraits(units, invalid_assets):
    portraits = {}
    for u in units:
        portrait_img = load_image_safe(u.portrait_path, invalid_assets)
        portraits[u.name] = portrait_img if portrait_img else create_portrait_surface(u.color, u.name)
    return portraits

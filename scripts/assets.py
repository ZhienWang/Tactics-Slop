import math
import os
import sys
import random
import pygame
from scripts.config import SCREEN_WIDTH, SCREEN_HEIGHT, TILE_WIDTH, TILE_HEIGHT


# Papyrus itself is a proprietary font, so it can't be bundled with the
# game. Metamorphous (SIL Open Font License - free to bundle and
# redistribute, including commercially) is the closest free lookalike:
# a rough, hand-carved, ancient-script feel similar to Papyrus's own
# irregular strokes. Bundling the actual file means every player sees the
# same look, rather than only players who happen to have Papyrus installed.
TEXT_FONT_PATH = "assets/fonts/Metamorphous-Regular.ttf"
TEXT_FONT_NAME = "papyrus"  # SysFont fallback if the bundled file can't be loaded
# Metamorphous (like Papyrus) renders roughly twice as wide/tall per point
# size as the default system font every box width, wrap width, and text
# position in this game was originally tuned against - without this, text
# overflows panels and overlaps neighboring UI everywhere. This brings it
# back to roughly the same footprint as the original text at the same size.
PAPYRUS_SIZE_SCALE = 0.5

_font_cache = {}


def get_font(size, bold=False):
    """The single place every on-screen font is created, so the game's text
    style is a one-line change rather than a find-and-replace across every
    draw function. Fonts are cached by (size, bold) since this is called
    every frame from several draw functions."""
    scaled_size = max(8, round(size * PAPYRUS_SIZE_SCALE))
    cache_key = (scaled_size, bold)
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    font_path = TEXT_FONT_PATH
    if not os.path.isabs(font_path):
        font_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), font_path)
    try:
        font = pygame.font.Font(font_path, scaled_size)
        font.set_bold(bold)
    except (FileNotFoundError, OSError):
        font = pygame.font.SysFont(TEXT_FONT_NAME, scaled_size, bold=bold)

    _font_cache[cache_key] = font
    return font


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


UI_FRAME_DIR = "assets/ui_frame"
UI_FRAME_INTERIOR = (46, 33, 23)
UI_FRAME_BORDER_PX = 30
_NINE_SLICE_PIECES = ["corner_tl", "corner_tr", "corner_bl", "corner_br", "edge_top", "edge_bottom", "edge_left", "edge_right"]


def load_nine_slice_frame(invalid_paths=None):
    """Loads the 8 corner/edge pieces of the game's ornate wooden UI frame
    (cut from assets/frame_example.jpg, a reference image the user provided
    for the look they wanted). Returns a dict keyed by piece name, or an
    empty dict if the assets are missing - callers should fall back to a
    plain rect panel in that case."""
    pieces = {}
    for name in _NINE_SLICE_PIECES:
        image = load_image_safe(f"{UI_FRAME_DIR}/{name}.png", invalid_paths)
        if image is None:
            return {}
        pieces[name] = image
    return pieces


def _frame_corner_size(rect, frame):
    """Corners always scale down as one square unit (never stretched
    independently in x/y - that would visibly distort the bracket art).
    Held to a fixed thin border thickness (UI_FRAME_BORDER_PX) regardless of
    panel size, except on a small panel where that would eat too much of it
    - there it's capped to 40% of the shorter side instead, so there's
    always real interior left for content."""
    w, h = rect[2], rect[3]
    native = frame["corner_tl"].get_size()[0]
    size = min(native, UI_FRAME_BORDER_PX, int(min(w, h) * 0.4))
    return max(1, size)


def frame_content_rect(rect, frame):
    """The usable interior rect inside a nine-slice frame (same corner-size
    math draw_nine_slice_panel uses) - callers should inset any dividers,
    text, or extra decoration to this rect rather than the panel's full
    bounds, or they'll be drawn cutting across the ornate wood border."""
    x, y, w, h = rect
    if not frame:
        return pygame.Rect(x, y, w, h)
    corner = _frame_corner_size(rect, frame)
    return pygame.Rect(x + corner, y + corner, max(1, w - 2 * corner), max(1, h - 2 * corner))


def draw_nine_slice_panel(surface, rect, frame, interior_color=UI_FRAME_INTERIOR):
    """Draws the ornate wooden frame around `rect`: corners at native size,
    edges stretched to fit, with a flat-colored interior showing through
    (pass interior_color=None to leave the interior for the caller to draw
    into instead)."""
    x, y, w, h = rect
    corner_w = corner_h = _frame_corner_size(rect, frame)
    inner_w = max(1, w - 2 * corner_w)
    inner_h = max(1, h - 2 * corner_h)

    if interior_color is not None:
        pygame.draw.rect(surface, interior_color, (x + corner_w, y + corner_h, inner_w, inner_h))

    surface.blit(pygame.transform.smoothscale(frame["edge_top"], (inner_w, corner_h)), (x + corner_w, y))
    surface.blit(pygame.transform.smoothscale(frame["edge_bottom"], (inner_w, corner_h)), (x + corner_w, y + h - corner_h))
    surface.blit(pygame.transform.smoothscale(frame["edge_left"], (corner_w, inner_h)), (x, y + corner_h))
    surface.blit(pygame.transform.smoothscale(frame["edge_right"], (corner_w, inner_h)), (x + w - corner_w, y + corner_h))

    surface.blit(pygame.transform.smoothscale(frame["corner_tl"], (corner_w, corner_h)), (x, y))
    surface.blit(pygame.transform.smoothscale(frame["corner_tr"], (corner_w, corner_h)), (x + w - corner_w, y))
    surface.blit(pygame.transform.smoothscale(frame["corner_bl"], (corner_w, corner_h)), (x, y + h - corner_h))
    surface.blit(pygame.transform.smoothscale(frame["corner_br"], (corner_w, corner_h)), (x + w - corner_w, y + h - corner_h))


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
    font = get_font(size // 2)
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


TRUNK_COLOR = (104, 68, 40)
TRUNK_SHADE_COLOR = (74, 47, 27)
# Three canopy tones, lit from above like the tiles' own shading (their top
# face full brightness, the +rx-facing wall 0.7, the +ry-facing one 0.5).
CANOPY_COLORS = [(58, 104, 48), (74, 132, 58), (104, 168, 74)]
_tree_sprite_cache = {}


def build_tree_sprite(width, height, seed=0):
    """A simple standing tree: a trunk under three stacked canopy blobs,
    drawn from scratch in the same flat-shaded style as the terrain tile
    art (no tree texture ships with the game). `height` is the full sprite
    height in pixels; callers size it from the prop's map height so a
    3-height tree really does stand three height units above its tile.
    Cached, since this is called every frame for every prop on the map."""
    cache_key = (width, height, seed)
    if cache_key in _tree_sprite_cache:
        return _tree_sprite_cache[cache_key]

    rng = random.Random(seed)
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    trunk_width = max(3, round(width * 0.16))
    trunk_height = round(height * 0.34)
    trunk_x = (width - trunk_width) // 2
    trunk_y = height - trunk_height
    pygame.draw.rect(surface, TRUNK_SHADE_COLOR, (trunk_x, trunk_y, trunk_width, trunk_height))
    pygame.draw.rect(surface, TRUNK_COLOR, (trunk_x, trunk_y, max(1, round(trunk_width * 0.55)), trunk_height))

    # Widest blob at the base of the canopy, narrowing toward the crown, each
    # one nudged sideways a little so no two trees are identical.
    canopy_height = height - trunk_height
    for index, (center_frac, width_frac) in enumerate([(0.78, 1.0), (0.5, 0.86), (0.22, 0.62)]):
        blob_width = max(4, round(width * width_frac))
        blob_height = max(4, round(canopy_height * 0.52))
        drift = rng.randint(-1, 1) * max(1, round(width * 0.04))
        center_x = width // 2 + drift
        center_y = round(canopy_height * center_frac)
        rect = pygame.Rect(0, 0, blob_width, blob_height)
        rect.center = (center_x, center_y)
        pygame.draw.ellipse(surface, CANOPY_COLORS[0], rect)
        lit = rect.inflate(-round(blob_width * 0.22), -round(blob_height * 0.3))
        lit.move_ip(-round(blob_width * 0.06), -round(blob_height * 0.12))
        pygame.draw.ellipse(surface, CANOPY_COLORS[1], lit)
        if index == 2:
            crown = lit.inflate(-round(blob_width * 0.4), -round(blob_height * 0.4))
            pygame.draw.ellipse(surface, CANOPY_COLORS[2], crown)

    _tree_sprite_cache[cache_key] = surface
    return surface


# Rock tones, lit from above-left like the canopy: the shaded right face,
# the lit left face, the top, a brighter chiseled facet on the top, and the
# dark edge line that picks the facets out from one another.
BOULDER_COLORS = [(84, 80, 76), (122, 117, 110), (152, 147, 138), (178, 173, 163), (52, 49, 46)]
_boulder_sprite_cache = {}


def build_boulder_sprite(width, height, seed=0):
    """A blocky, faceted rock in the style of Final Fantasy Tactics: its
    base follows the lower two edges of the isometric tile diamond so it
    sits square on its tile, straight walls rise from there (lit left face,
    shaded right face), and an irregular chiseled crown caps it. The bottom
    point of the sprite is the tile diamond's front corner of the rock's
    footprint. Seeded so each rock's crown differs but stays stable frame
    to frame. Cached."""
    cache_key = (width, height, seed)
    if cache_key in _boulder_sprite_cache:
        return _boulder_sprite_cache[cache_key]

    rng = random.Random(seed)
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    right, bottom = width - 1, height - 1
    center_x = right / 2
    # The footprint diamond is half as tall as it is wide, like the tiles.
    diamond_drop = width / 4
    side_y = bottom - diamond_drop
    # Wall heights: whatever the sprite has left once the top face (a full
    # diamond, twice diamond_drop tall) is reserved. The side corners come
    # out a little uneven so the block doesn't read as a perfect cube.
    wall = max(2.0, bottom - diamond_drop * 2)
    front_top = bottom - wall * rng.uniform(0.9, 1.0)
    left_top = side_y - wall * rng.uniform(0.75, 0.95)
    right_top = side_y - wall * rng.uniform(0.7, 0.9)

    base_left, base_front, base_right = (0, side_y), (center_x, bottom), (right, side_y)
    wall_left, wall_front, wall_right = (0, left_top), (center_x, front_top), (right, right_top)

    # The crown: the back half of a slightly tilted, uneven top face - the
    # back corners of the footprint diamond lifted a little off true, so the
    # top reads as a flat-ish slab of chiseled stone rather than a roof.
    back_y = front_top - diamond_drop * 2
    crown = [
        (right * rng.uniform(0.84, 0.92), right_top - diamond_drop * rng.uniform(0.7, 0.95)),
        (center_x + right * rng.uniform(0.02, 0.1), back_y + rng.uniform(-1, 2)),
        (center_x - right * rng.uniform(0.06, 0.14), back_y + rng.uniform(0, 3)),
        (right * rng.uniform(0.08, 0.16), left_top - diamond_drop * rng.uniform(0.7, 0.95)),
    ]
    crown = [(x, max(0, y)) for x, y in crown]

    left_face = [base_left, base_front, wall_front, wall_left]
    right_face = [base_front, base_right, wall_right, wall_front]
    top = [wall_left, wall_front, wall_right] + crown
    # A brighter facet on the sunlit side of the crown: from the front edge
    # back to the peak and down the left shoulder.
    facet = [wall_front, crown[2], crown[3], wall_left]

    pygame.draw.polygon(surface, BOULDER_COLORS[0], right_face)
    pygame.draw.polygon(surface, BOULDER_COLORS[1], left_face)
    pygame.draw.polygon(surface, BOULDER_COLORS[2], top)
    pygame.draw.polygon(surface, BOULDER_COLORS[3], facet)

    edge = BOULDER_COLORS[4]
    pygame.draw.lines(surface, edge, True, [base_left, base_front, base_right, wall_right] + crown + [wall_left])
    pygame.draw.line(surface, edge, base_front, wall_front)
    pygame.draw.lines(surface, edge, False, [wall_left, wall_front, wall_right])

    _boulder_sprite_cache[cache_key] = surface
    return surface


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


def terrain_top_face(image):
    """Just the diamond top face of a terrain tile sprite, with its baked-in
    side edges cut away. Every terrain texture is drawn as a small isometric
    slab - a top face over two darker side faces - so the silhouette's full
    height is the top face plus the slab's thickness, and the thickness is
    how tall the silhouette is at its outer edge. Slope tiles texture their
    ramp with this: shearing the whole slab, sides and all, reads as a
    tilted block sitting on the hill rather than a ramp."""
    mask = pygame.mask.from_surface(image)
    bounds = mask.get_bounding_rects()
    if not bounds:
        return image
    rect = bounds[0].unionall(bounds[1:])
    edge_x = min(rect.left + 2, rect.right - 1)
    edge_rows = [y for y in range(rect.top, rect.bottom) if mask.get_at((edge_x, y))]
    thickness = edge_rows[-1] - edge_rows[0] if edge_rows else 0
    face = image.subsurface((rect.left, rect.top, rect.width, max(1, rect.height - thickness))).copy()
    width, height = face.get_size()
    diamond = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.polygon(diamond, (255, 255, 255, 255), [(width / 2, 0), (width, height / 2), (width / 2, height), (0, height / 2)])
    face.blit(diamond, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return face


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
            # 2:1 like every unit image; kept at twice the 140x70 map slot
            # so the refined unit art (assets/unit_art.py) stays crisp when
            # the map is zoomed in.
            portraits[u.name] = pygame.transform.smoothscale(portrait_img, (280, 140))
        else:
            portraits[u.name] = create_portrait_surface(u.color, u.name)
    return portraits


CHESS_PIECE_DIR = "assets/chess_pieces"

# Maps each job class to the chess piece that best fits its role - crowned
# leader, powerful support, clergy, mobile fighter, ranged/fixed power, and
# rank-and-file, respectively. See assets/chess_pieces/CREDITS.txt for the
# art's source/license (Cburnett's SVG chess set on Wikimedia Commons).
CHESS_PIECE_BY_CLASS = {
    "Missionary": "king",
    "Officer": "queen",
    "Apostle": "bishop",
    "Sergeant": "knight",
    "Archer": "rook",
    "Soldier": "pawn",
    "Shieldbearer": "pawn",
    "Medic": "bishop",
}


def build_character_chess_art(units, invalid_assets):
    """On-map unit art as classic chess pieces instead of each character's
    own small icon - piece type reflects the unit's job class, and
    light/dark matches the Player/Enemy side, same as a real chess set.
    Falls back to build_character_portraits' icon for any class without a
    mapped piece (or if the piece art fails to load)."""
    chess_art = {}
    for u in units:
        piece = CHESS_PIECE_BY_CLASS.get(u.char_class)
        if not piece:
            continue
        color = "light" if u.team == "Player" else "dark"
        piece_img = load_image_safe(f"{CHESS_PIECE_DIR}/{piece}_{color}.png", invalid_assets)
        if piece_img:
            chess_art[u.name] = piece_img
    fallback = build_character_portraits(
        [u for u in units if u.name not in chess_art], invalid_assets
    )
    chess_art.update(fallback)
    return chess_art


PIXEL_UNIT_DIR = "assets/pixel_units"
# The bundled CC0 pack (see assets/pixel_units/CREDITS.txt) only has these
# three base classes - the other three job classes borrow whichever one
# fits their role best, since a chibi human sprite reads fine at on-map
# icon size regardless of the exact job title.
PIXEL_UNIT_BY_CLASS = {
    "Missionary": "cleric",
    "Apostle": "cleric",
    "Officer": "fighter",
    "Sergeant": "fighter",
    "Soldier": "fighter",
    "Archer": "mage",
    "Shieldbearer": "fighter",
    "Medic": "cleric",
}
# Multiplied onto the Enemy side's sprite so the two teams read apart at a
# glance on a crowded board, the same trick already used for Centurion
# Marcus's gold-tinted portrait.
ENEMY_UNIT_TINT = (255, 210, 200, 255)


def build_character_pixel_art(units, invalid_assets):
    """On-map unit art as small FFT-style chibi pixel-art sprites instead
    of each character's own icon - sprite reflects the unit's job class
    (see PIXEL_UNIT_BY_CLASS), and the Enemy side gets a red tint to read
    apart from the Player side at a glance. Falls back to
    build_character_portraits' icon for any class without a mapped sprite
    (or if the sprite art fails to load)."""
    pixel_art = {}
    for u in units:
        sprite_name = PIXEL_UNIT_BY_CLASS.get(u.char_class)
        if not sprite_name:
            continue
        sprite_img = load_image_safe(f"{PIXEL_UNIT_DIR}/{sprite_name}.png", invalid_assets)
        if not sprite_img:
            continue
        if u.team != "Player":
            tint = pygame.Surface(sprite_img.get_size(), pygame.SRCALPHA)
            tint.fill(ENEMY_UNIT_TINT)
            sprite_img = sprite_img.copy()
            sprite_img.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        pixel_art[u.name] = sprite_img
    fallback = build_character_portraits(
        [u for u in units if u.name not in pixel_art], invalid_assets
    )
    pixel_art.update(fallback)
    return pixel_art


FACE_PORTRAIT_DIR = "assets/portraits"


def build_character_face_portraits(units, invalid_assets):
    """Higher-detail character-screen portraits (world map roster/equipment/
    books screens, the in-battle turn order strip, action menu and unit
    profile box) - distinct from build_character_portraits' small on-map
    battle token, which stays a simple icon so units don't visually clutter
    the tactical grid. Looked up by the portrait_path's filename under
    FACE_PORTRAIT_DIR; falls back to the on-map icon (or its own generated
    silhouette) for any unit without a dedicated face portrait, e.g. generic
    Legionnaires."""
    face_portraits = {}
    for u in units:
        # A unit-specific face (e.g. a converted Legionnaire's) comes first.
        face_img = load_image_safe(u.face_portrait_path) if getattr(u, "face_portrait_path", None) else None
        face_path = f"{FACE_PORTRAIT_DIR}/{os.path.basename(u.portrait_path)}" if u.portrait_path else None
        if face_img is None and face_path:
            face_img = load_image_safe(face_path)
        if face_img:
            face_portraits[u.name] = pygame.transform.smoothscale(face_img, (140, 70))
    fallback = build_character_portraits(
        [u for u in units if u.name not in face_portraits], invalid_assets
    )
    face_portraits.update(fallback)
    return face_portraits

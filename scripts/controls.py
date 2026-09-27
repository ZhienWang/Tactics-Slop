from scripts.config import TILE_WIDTH, TILE_HEIGHT, TILE_RISE


def point_in_polygon(point, polygon):
    x, y = point
    inside = False
    for i in range(len(polygon)):
        j = (i - 1) % len(polygon)
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-6) + xi)
        if intersect:
            inside = not inside
    return inside


def rotate_grid_position(x, y, rotation, map_cols, map_rows):
    if rotation == 1:
        return y, map_rows - 1 - x
    if rotation == 2:
        return map_cols - 1 - x, map_rows - 1 - y
    if rotation == 3:
        return map_cols - 1 - y, x
    return x, y


def is_slope_height(height):
    return height % 1 == 0.5


def slope_uphill_direction(map_data, x, y, height=None):
    """Which way a half-height (x.5) tile's ramp rises, as a map-space
    (dx, dy) step toward the neighbor it climbs to. Only a neighbor taller
    than the tile can be climbed to, and of those it picks the one whose
    opposite neighbor is lowest, so a 0.5 tile between a 0 tile and a 1
    tile joins both edges seamlessly. Returns None for whole heights, and
    for a half-height tile with no taller neighbor to ramp up to (e.g. a
    lone 0.5 on flat ground) - that one just draws as a flat half-step.
    `height` overrides map_data[y][x], for a tile stacked above its
    column's topmost height (a map editor bridge layer)."""
    if height is None:
        height = map_data[y][x]
    if not is_slope_height(height):
        return None
    rows = len(map_data)
    cols = len(map_data[0]) if rows else 0

    def neighbor_height(nx, ny):
        if 0 <= nx < cols and 0 <= ny < rows:
            return map_data[ny][nx]
        return height

    best_direction, best_rise = None, 0
    for dx, dy in [(1, 0), (0, 1), (-1, 0), (0, -1)]:
        uphill_height = neighbor_height(x + dx, y + dy)
        if uphill_height <= height:
            continue
        rise = uphill_height - neighbor_height(x - dx, y - dy)
        if rise > best_rise:
            best_direction, best_rise = (dx, dy), rise
    return best_direction


# Where each on-screen top corner (top, right, bottom, left) of a tile sits
# relative to the tile's center, in rotated grid space - the top corner is
# the tile's (rx, ry) grid corner, the bottom one is (rx + 1, ry + 1).
TILE_CORNER_GRID_OFFSETS = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
FLAT_CORNER_OFFSETS = (0, 0, 0, 0)


def tile_corner_offsets(map_data, x, y, rotation=0, height=None):
    """Height of each of a tile's top corners (top, right, bottom, left)
    relative to the tile's own height: all 0 for a flat tile, and for a
    slope -0.5 along its low edge and +0.5 along its high edge. Depends on
    rotation, since turning the camera changes which on-screen corners
    face uphill."""
    direction = slope_uphill_direction(map_data, x, y, height)
    if direction is None:
        return FLAT_CORNER_OFFSETS
    rows = len(map_data)
    cols = len(map_data[0]) if rows else 0
    rx, ry = rotate_grid_position(x, y, rotation, cols, rows)
    uphill_rx, uphill_ry = rotate_grid_position(x + direction[0], y + direction[1], rotation, cols, rows)
    drx, dry = uphill_rx - rx, uphill_ry - ry
    return tuple(drx * cx + dry * cy for cx, cy in TILE_CORNER_GRID_OFFSETS)


def tile_top_points(sx, sy, zoom=1.0, corner_offsets=FLAT_CORNER_OFFSETS):
    """Screen polygon of a tile's top face (top, right, bottom, left),
    with each corner raised or lowered by its height offset - a flat
    diamond unless corner_offsets tilts it into a slope."""
    tile_width = TILE_WIDTH * zoom
    tile_height = TILE_HEIGHT * zoom
    rise = TILE_RISE * zoom
    flat_points = [
        (sx, sy),
        (sx + tile_width / 2, sy + tile_height / 2),
        (sx, sy + tile_height),
        (sx - tile_width / 2, sy + tile_height / 2)
    ]
    return [(px, py - offset * rise) for (px, py), offset in zip(flat_points, corner_offsets)]


def screen_to_map(mx, my, origin_x, origin_y, map_data, rotation=0, zoom=1.0):
    # map_data: 2D list [row][col] heights
    MAP_ROWS = len(map_data)
    MAP_COLS = len(map_data[0]) if MAP_ROWS else 0
    last_hit = None
    for y in range(MAP_ROWS):
        for x in range(MAP_COLS):
            z = map_data[y][x]
            rx, ry = rotate_grid_position(x, y, rotation, MAP_COLS, MAP_ROWS)
            tile_width = TILE_WIDTH * zoom
            tile_height = TILE_HEIGHT * zoom
            sx = origin_x + (rx - ry) * (tile_width / 2)
            sy = origin_y + (rx + ry) * (tile_height / 2) - (z * TILE_RISE * zoom)
            top_points = tile_top_points(sx, sy, zoom, tile_corner_offsets(map_data, x, y, rotation))
            if point_in_polygon((mx, my), top_points):
                last_hit = (x, y)
    return last_hit

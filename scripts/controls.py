from scripts.config import TILE_WIDTH, TILE_HEIGHT


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
            sy = origin_y + (rx + ry) * (tile_height / 2) - (z * 14 * zoom)
            top_points = [
                (sx, sy),
                (sx + tile_width / 2, sy + tile_height / 2),
                (sx, sy + tile_height),
                (sx - tile_width / 2, sy + tile_height / 2)
            ]
            if point_in_polygon((mx, my), top_points):
                last_hit = (x, y)
    return last_hit

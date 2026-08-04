from config import TILE_WIDTH, TILE_HEIGHT


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


def screen_to_map(mx, my, origin_x, origin_y, map_data):
    # map_data: 2D list [row][col] heights
    MAP_ROWS = len(map_data)
    MAP_COLS = len(map_data[0]) if MAP_ROWS else 0
    last_hit = None
    for y in range(MAP_ROWS):
        for x in range(MAP_COLS):
            z = map_data[y][x]
            sx = origin_x + (x - y) * (TILE_WIDTH // 2)
            sy = origin_y + (x + y) * (TILE_HEIGHT // 2) - (z * 14)
            top_points = [
                (sx, sy),
                (sx + TILE_WIDTH // 2, sy + TILE_HEIGHT // 2),
                (sx, sy + TILE_HEIGHT),
                (sx - TILE_WIDTH // 2, sy + TILE_HEIGHT // 2)
            ]
            if point_in_polygon((mx, my), top_points):
                last_hit = (x, y)
    return last_hit

import pygame

# --- DISPLAY / TILE CONFIG ---
SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 900
TILE_WIDTH = 64
TILE_HEIGHT = 32
# Screen pixels (at zoom 1) that one unit of map height raises a tile by.
TILE_RISE = 14

# --- THEME COLORS ---
BG_COLOR = (25, 25, 35)
GRID_COLOR = (80, 80, 90)
CURSOR_COLOR = (255, 215, 0)

# --- FAITH / CONVERSION ---
FAITH_CAP = 200

CHARACTER_PORTRAITS = {}

CLASS_SKILLSETS = {
    "Archer": ["Attack", "Shoot"],
    "Mage": ["Fire", "Blizzard"],
    "Knight": ["Attack", "Chakra"]
}

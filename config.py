import pygame

# --- DISPLAY / TILE CONFIG ---
SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 700
TILE_WIDTH = 64
TILE_HEIGHT = 32

# --- THEME COLORS ---
BG_COLOR = (25, 25, 35)
GRID_COLOR = (80, 80, 90)
CURSOR_COLOR = (255, 215, 0)

CHARACTER_PORTRAITS = {}

CLASS_SKILLSETS = {
    "Archer": ["Attack", "Fire"],
    "Mage": ["Fire", "Blizzard"],
    "Knight": ["Attack", "Chakra"]
}

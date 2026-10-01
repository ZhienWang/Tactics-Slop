"""Module entrypoint: the title screen (New Game runs the class survey),
then the first stage's battle.

The world map is hidden for now - scripts/world_map.py is untouched and
still runnable on its own; swapping run_first_stage back for world_map's
main here (and in main.py) is all it takes to put it back in front.
"""
import sys
import asyncio
import pygame
from scripts.intro import start_game


if __name__ == '__main__':
    asyncio.run(start_game())
    pygame.quit()
    sys.exit()

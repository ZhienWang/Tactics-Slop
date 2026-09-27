"""Module entrypoint: boots straight into the first stage's battle.

The world map is hidden for now - scripts/world_map.py is untouched and
still runnable on its own; swapping run_first_stage back for world_map's
main here (and in main.py) is all it takes to put it back in front.
"""
import sys
import asyncio
import pygame
from scripts.game_logic import run_first_stage


if __name__ == '__main__':
    asyncio.run(run_first_stage())
    pygame.quit()
    sys.exit()

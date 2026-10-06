"""Module entrypoint: the title screen (New Game runs the class survey),
then the world map, where each story is told and its battle fought.
"""
import sys
import asyncio
import pygame
from scripts.intro import start_game


if __name__ == '__main__':
    asyncio.run(start_game())
    pygame.quit()
    sys.exit()

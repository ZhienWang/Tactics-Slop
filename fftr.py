"""Module entrypoint: boots straight into the world map."""
import sys
import asyncio
import pygame
from scripts.world_map import main


if __name__ == '__main__':
    asyncio.run(main())
    pygame.quit()
    sys.exit()

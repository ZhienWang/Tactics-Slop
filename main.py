"""Web entrypoint (pygbag): boots straight into the world map.

pygbag's generated loader hardcodes the entry file to `assets/main.py`
inside the packaged bundle, so this file must exist at the project root
under this exact name for the web build to actually start. Mirrors
fftr.py, the desktop entrypoint.
"""
import sys
import asyncio
import pygame
from scripts.world_map import main


if __name__ == '__main__':
    asyncio.run(main())
    pygame.quit()
    sys.exit()

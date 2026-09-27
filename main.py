"""Web entrypoint (pygbag): boots straight into the first stage's battle.

pygbag's generated loader hardcodes the entry file to `assets/main.py`
inside the packaged bundle, so this file must exist at the project root
under this exact name for the web build to actually start. Mirrors
fftr.py, the desktop entrypoint - including the world map being hidden
for now (see fftr.py).
"""
import sys
import asyncio
import pygame
from scripts.game_logic import run_first_stage


if __name__ == '__main__':
    asyncio.run(run_first_stage())
    pygame.quit()
    sys.exit()

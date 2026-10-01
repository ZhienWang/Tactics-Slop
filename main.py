"""Web entrypoint (pygbag): the title screen (New Game runs the class survey),
then the first stage's battle.

pygbag's generated loader hardcodes the entry file to `assets/main.py`
inside the packaged bundle, so this file must exist at the project root
under this exact name for the web build to actually start. Mirrors
fftr.py, the desktop entrypoint - including the world map being hidden
for now (see fftr.py).

Build the web version with tools/build_web.py.
"""
import asyncio
import pygame
from scripts.intro import start_game


async def main():
    await start_game()
    # Shut pygame down only once the game is actually over. In the browser
    # asyncio.run() returns immediately (the game keeps running on the
    # page's event loop), so cleanup placed *after* asyncio.run() - as the
    # desktop entrypoint can - would tear pygame down before the first frame.
    pygame.quit()


if __name__ == '__main__':
    asyncio.run(main())

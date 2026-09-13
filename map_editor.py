"""Standalone map-editing tool entrypoint."""
import sys
import pygame
from scripts.map_editor import main


if __name__ == '__main__':
    main()
    pygame.quit()
    sys.exit()

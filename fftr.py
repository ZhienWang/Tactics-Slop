"""Module entrypoint: boots straight into the world map."""
import sys
import pygame
from scripts.world_map import main


if __name__ == '__main__':
    main()
    pygame.quit()
    sys.exit()

import pygame
import sys
import json
import os
from src.utils import WINDOW_WIDTH, WINDOW_HEIGHT, FPS
from src.game import Game

def load_config():
    config_path = os.path.join("data", "config.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"sound": True, "music": True, "fullscreen": False, "volume": 0.8}

def main():
    pygame.init()
    config = load_config()
    
    flags = pygame.FULLSCREEN if config.get("fullscreen", False) else 0
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), flags)
    pygame.display.set_caption("Siglo - Juego Tradicional")
    
    clock = pygame.time.Clock()
    game = Game(screen)
    
    while True:
        events = pygame.event.get()
        game.handle_events(events)
        game.update()
        game.render()
        clock.tick(FPS)

if __name__ == "__main__":
    main()

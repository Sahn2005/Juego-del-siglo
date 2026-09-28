"""Cliente multijugador de Siglo (abre directamente la pantalla de conexión).

Uso:
    python cliente.py

También se puede entrar desde el botón MULTIJUGADOR de siglo_game/main.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "siglo_game"))

import pygame                                   # noqa: E402
from src.utils import WINDOW_WIDTH, WINDOW_HEIGHT, FPS  # noqa: E402
from src.ui import UI                           # noqa: E402
from src.online import OnlineGame               # noqa: E402


def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Siglo - Multijugador")
    clock = pygame.time.Clock()

    ui = UI(screen)
    online = OnlineGame(screen, ui)

    while not online.wants_exit:
        events = pygame.event.get()
        if any(e.type == pygame.QUIT for e in events):
            break
        online.handle_events(events)
        online.update()
        ui.clear()
        online.draw()
        pygame.display.flip()
        clock.tick(FPS)

    online.close()
    pygame.quit()


if __name__ == "__main__":
    main()

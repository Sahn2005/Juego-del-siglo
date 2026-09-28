import pygame
from src.utils import *
from src import board_ui

class Button:
    def __init__(self, x, y, width, height, text, font, color, hover_color):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.is_hovered = False

    def draw(self, surface):
        color = self.hover_color if self.is_hovered else self.color
        shadow = self.rect.move(0, 3)
        pygame.draw.rect(surface, (0, 0, 0, 60), shadow, border_radius=10)
        pygame.draw.rect(surface, color, self.rect, border_radius=10)
        # una franja más clara arriba, para dar un poco de volumen al botón
        top_strip = self.rect.copy()
        top_strip.height = max(2, self.rect.height // 3)
        pygame.draw.rect(surface, board_ui.lighten(color, 0.18), top_strip,
                         border_top_left_radius=10, border_top_right_radius=10)
        pygame.draw.rect(surface, board_ui.darken(color, 0.55), self.rect, 2, border_radius=10)

        text_surf = self.font.render(self.text, True, WHITE)
        text_rect = text_surf.get_rect(center=self.rect.center)
        shadow_surf = self.font.render(self.text, True, board_ui.darken(color, 0.6))
        surface.blit(shadow_surf, text_rect.move(0, 1))
        surface.blit(text_surf, text_rect)

    def check_hover(self, mouse_pos):
        self.is_hovered = self.rect.collidepoint(mouse_pos)
        
    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.is_hovered:
                return True
        return False

class UI:
    """
    Handles all visual rendering using Pygame.
    """
    def __init__(self, screen):
        self.screen = screen
        pygame.font.init()
        self.title_font = pygame.font.SysFont("Arial", 60, bold=True)
        self.font = pygame.font.SysFont("Arial", 32)
        self.small_font = pygame.font.SysFont("Arial", 24)
        self.score_font = pygame.font.SysFont("Arial", 38, bold=True)
        
    def draw_text(self, text, font, color, x, y, center=False):
        surf = font.render(text, True, color)
        rect = surf.get_rect()
        if center:
            rect.center = (x, y)
        else:
            rect.topleft = (x, y)
        self.screen.blit(surf, rect)
        
    def clear(self):
        self.screen.fill(BACKGROUND_COLOR)

    def draw_table_felt(self):
        """Fondo de paño verde con baranda, para las pantallas 'en la mesa'."""
        board_ui.draw_felt_background(self.screen)

    def draw_table_header(self, title="SIGLO", subtitle=None, corner_text=None, y=44):
        board_ui.draw_table_header(self.screen, self, title, subtitle, corner_text, y)

    def draw_player_board(self, players, current_turn_idx, winners=None):
        """Dibuja la tarjeta de cada jugador (solo el modo solitario la usa)."""
        winners = winners or []
        rects = board_ui.card_rects(len(players))
        for i, (player, rect) in enumerate(zip(players, rects)):
            board_ui.draw_player_card(
                self.screen, self, rect,
                name=player.name,
                score=player.score,
                status=player.status,
                balls=[b.value for b in player.hand],
                is_turn=(i == current_turn_idx),
                is_winner=(player in winners),
                is_me=(not player.is_ai),
            )

import pygame
import sys
from src.utils import *
from src.ui import UI, Button
from src.player import Player
from src.deck import Deck
from src.rules import Rules
from src.ai import AI
from src.online import OnlineGame
from src import board_ui

class Game:
    """
    Manages the game state machine and coordinates logic and UI.
    """
    def __init__(self, screen):
        self.screen = screen
        self.ui = UI(screen)
        self.state = STATE_MENU
        self.players = []
        self.deck = Deck()
        self.current_turn_idx = 0
        self.num_players = 3 # Default 1 human, 2 AI
        self.online = None # OnlineGame mientras se está en modo multijugador
        
        # Buttons Menu
        self.btn_play = Button(WINDOW_WIDTH//2 - 130, 280, 260, 50, "JUGAR", self.ui.font, PRIMARY_COLOR, SECONDARY_COLOR)
        self.btn_online = Button(WINDOW_WIDTH//2 - 130, 360, 260, 50, "MULTIJUGADOR", self.ui.font, PRIMARY_COLOR, SECONDARY_COLOR)
        self.btn_rules = Button(WINDOW_WIDTH//2 - 130, 440, 260, 50, "REGLAS", self.ui.font, PRIMARY_COLOR, SECONDARY_COLOR)
        self.btn_quit = Button(WINDOW_WIDTH//2 - 130, 520, 260, 50, "SALIR", self.ui.font, RED, SECONDARY_COLOR)

        # Buttons Playing
        self.btn_bola = Button(WINDOW_WIDTH//2 - 150, 650, 120, 50, "BOLA", self.ui.font, PRIMARY_COLOR, SECONDARY_COLOR)
        self.btn_me_quedo = Button(WINDOW_WIDTH//2 + 30, 650, 160, 50, "ME QUEDO", self.ui.font, RED, SECONDARY_COLOR)
        
        # Buttons Generic
        self.btn_back = Button(20, 20, 100, 40, "VOLVER", self.ui.small_font, PRIMARY_COLOR, SECONDARY_COLOR)
        
        self.winners = []

    def start_game(self, num_players=3):
        self.players = [Player("Jugador 1", is_ai=False)]
        for i in range(1, num_players):
            self.players.append(Player(f"IA {i+1}", is_ai=True))
        
        self.reset_round()
        self.state = STATE_PLAYING

    def reset_round(self):
        self.deck = Deck()
        for p in self.players:
            p.reset_round()
            p.add_ball(self.deck.draw()) # Give Vira
            p.status = "PLAYING"
        self.current_turn_idx = 0
        self.ai_last_action_time = pygame.time.get_ticks()

    def get_current_player(self):
        return self.players[self.current_turn_idx]

    def next_turn(self):
        start_idx = self.current_turn_idx
        while True:
            self.current_turn_idx = (self.current_turn_idx + 1) % len(self.players)
            if self.players[self.current_turn_idx].status == "PLAYING":
                self.ai_last_action_time = pygame.time.get_ticks()
                break
            if self.current_turn_idx == start_idx:
                self.end_round()
                break

    def end_round(self):
        self.winners = Rules.determine_round_winners(self.players)
        self.state = STATE_ROUND_END

    def close_online(self):
        """Sale del modo multijugador y vuelve al menú."""
        if self.online is not None:
            self.online.close()
            self.online = None
        self.state = STATE_MENU

    def handle_events(self, events):
        if self.state == STATE_ONLINE:
            for event in events:
                if event.type == pygame.QUIT:
                    self.close_online()
                    pygame.quit()
                    sys.exit()
            self.online.handle_events(events)
            if self.online.wants_exit:
                self.close_online()
            return

        mouse_pos = pygame.mouse.get_pos()
        for btn in [self.btn_play, self.btn_online, self.btn_rules, self.btn_quit, self.btn_bola, self.btn_me_quedo, self.btn_back]:
            btn.check_hover(mouse_pos)

        for event in events:
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
                
            if self.state == STATE_MENU:
                if self.btn_play.handle_event(event):
                    self.start_game(self.num_players)
                if self.btn_online.handle_event(event):
                    self.online = OnlineGame(self.screen, self.ui)
                    self.state = STATE_ONLINE
                if self.btn_rules.handle_event(event):
                    self.state = STATE_RULES
                if self.btn_quit.handle_event(event):
                    pygame.quit()
                    sys.exit()

            elif self.state == STATE_RULES or self.state == STATE_ROUND_END:
                if self.btn_back.handle_event(event):
                    self.state = STATE_MENU

            elif self.state == STATE_PLAYING:
                current_p = self.get_current_player()
                if not current_p.is_ai and current_p.status == "PLAYING":
                    if self.btn_bola.handle_event(event):
                        self.draw_ball_for_current()
                    if self.btn_me_quedo.handle_event(event):
                        current_p.status = "ME_QUEDO"
                        self.next_turn()

    def draw_ball_for_current(self):
        p = self.get_current_player()
        ball = self.deck.draw()
        if ball:
            p.add_ball(ball)
            Rules.evaluate_player_status(p)
            if p.status != "PLAYING":
                self.next_turn()

    def update(self):
        if self.state == STATE_ONLINE:
            self.online.update()
        elif self.state == STATE_PLAYING:
            current_p = self.get_current_player()
            if current_p.is_ai and current_p.status == "PLAYING":
                current_time = pygame.time.get_ticks()
                if current_time - getattr(self, 'ai_last_action_time', 0) > 1000:
                    self.ai_last_action_time = current_time
                    action = AI.decide_action(current_p.score)
                    if action == "BOLA":
                        self.draw_ball_for_current()
                    else:
                        current_p.status = "ME_QUEDO"
                        self.next_turn()

    def render(self):
        self.ui.clear()

        if self.state == STATE_MENU:
            self.ui.draw_text("SIGLO", self.ui.title_font, board_ui.darken(board_ui.FELT_LIGHT, 0.1),
                              WINDOW_WIDTH//2, 100, center=True)
            self.ui.draw_text("Juego tradicional colombiano", self.ui.font, TEXT_COLOR, WINDOW_WIDTH//2, 160, center=True)
            for value, dx in ((7, -70), (50, 0), (99, 70)):
                board_ui.draw_ball(self.ui.screen, self.ui.small_font, value,
                                   (WINDOW_WIDTH//2 + dx, 210), radius=22)
            self.btn_play.draw(self.ui.screen)
            self.btn_online.draw(self.ui.screen)
            self.btn_rules.draw(self.ui.screen)
            self.btn_quit.draw(self.ui.screen)

        elif self.state == STATE_RULES:
            self.ui.draw_text("REGLAS DE SIGLO", self.ui.title_font, TEXT_COLOR, WINDOW_WIDTH//2, 100, center=True)
            rules = [
                "1. Saca bolas para sumar puntos.",
                "2. Si sacas 99 o 100, logras SIGLO (ganas automáticamente si nadie te empata).",
                "3. Si pasas de 100, pierdes la ronda (ME FUI).",
                "4. Puedes detenerte (ME QUEDO) cuando quieras si estás en riesgo."
            ]
            for i, r in enumerate(rules):
                self.ui.draw_text(r, self.ui.small_font, TEXT_COLOR, WINDOW_WIDTH//2, 200 + i*40, center=True)
            self.btn_back.draw(self.ui.screen)

        elif self.state == STATE_PLAYING:
            self.ui.draw_table_felt()
            self.ui.draw_table_header("SIGLO")
            self.ui.draw_player_board(self.players, self.current_turn_idx)

            current_p = self.get_current_player()
            turn_text = "¡ES TU TURNO!" if not current_p.is_ai else f"Turno de {current_p.name}"
            turn_color = board_ui.GOLD if not current_p.is_ai else board_ui.CREAM_TEXT
            self.ui.draw_text(turn_text, self.ui.font, turn_color, WINDOW_WIDTH//2, 600, center=True)

            if not current_p.is_ai:
                self.btn_bola.draw(self.ui.screen)
                self.btn_me_quedo.draw(self.ui.screen)

        elif self.state == STATE_ONLINE:
            self.online.draw()

        elif self.state == STATE_ROUND_END:
            self.ui.draw_table_felt()
            self.ui.draw_table_header("SIGLO", subtitle="Fin de la ronda")
            self.ui.draw_player_board(self.players, -1, winners=self.winners)
            if self.winners:
                w_names = ", ".join([w.name for w in self.winners])
                text, color = f"Ganador(es): {w_names}", board_ui.GOLD
            else:
                text, color = "Todos se pasaron de 100 (ME FUI). Empate sin ganadores.", (230, 120, 120)
            font = self.ui.font if self.ui.font.size(text)[0] <= WINDOW_WIDTH - 40 else self.ui.small_font
            self.ui.draw_text(text, font, color, WINDOW_WIDTH//2, 600, center=True)
            self.btn_back.draw(self.ui.screen)

        pygame.display.flip()

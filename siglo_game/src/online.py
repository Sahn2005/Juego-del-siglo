"""Modo multijugador del cliente: formulario de conexión, sala de espera,
partida y resultado de la ronda.

OnlineGame tiene la misma forma que Game (handle_events / update / draw), así
que se puede usar dentro del menú principal o solo desde cliente.py.
El cliente no decide nada: envía lo que el jugador pide ("draw", "stay",
"start") y dibuja el estado que manda el servidor.
"""
import math
import time
from typing import Optional

import pygame

from src.utils import *
from src.ui import Button
from src.net_client import NetworkClient
from src.protocol import (
    MAX_NAME_LEN, MIN_PLAYERS,
    PHASE_LOBBY, PHASE_PLAYING, PHASE_ROUND_END,
    parse_address,
)
from src import board_ui

STAGE_FORM = "FORM"              # escribiendo servidor y nombre
STAGE_CONNECTING = "CONNECTING"  # esperando al servidor
STAGE_ONLINE = "ONLINE"          # dentro de la mesa (el estado lo da el servidor)

LEAVE_CONFIRM_SECONDS = 3.0
NOTICE_SECONDS = 3.0


class TextInput:
    """Campo de texto de una línea."""

    def __init__(self, x, y, width, height, placeholder="", max_len=40):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = ""
        self.placeholder = placeholder
        self.max_len = max_len
        self.active = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif (event.unicode and event.unicode.isprintable()
                  and len(self.text) + len(event.unicode) <= self.max_len):
                self.text += event.unicode

    def draw(self, surface, font):
        pygame.draw.rect(surface, WHITE, self.rect, border_radius=8)
        border, width = (PRIMARY_COLOR, 3) if self.active else (GRAY, 2)
        pygame.draw.rect(surface, border, self.rect, width, border_radius=8)

        if self.text or self.active:
            caret = "|" if self.active and (pygame.time.get_ticks() // 500) % 2 == 0 else ""
            surf = font.render(self.text + caret, True, TEXT_COLOR)
        else:
            surf = font.render(self.placeholder, True, GRAY)

        # Si el texto no cabe, se muestra el final (donde se está escribiendo).
        inner = self.rect.inflate(-20, 0)
        x = inner.x if surf.get_width() <= inner.width else inner.right - surf.get_width()
        previous_clip = surface.get_clip()
        surface.set_clip(inner)
        surface.blit(surf, (x, self.rect.centery - surf.get_height() // 2))
        surface.set_clip(previous_clip)


class OnlineGame:
    def __init__(self, screen, ui):
        self.screen = screen
        self.ui = ui
        self.wants_exit = False   # True cuando el usuario pide volver al menú

        self.stage = STAGE_FORM
        self.net: Optional[NetworkClient] = None
        self.my_id: Optional[int] = None
        self.snapshot: Optional[dict] = None   # último estado recibido
        self.snapshot_at = 0.0                 # momento (monotonic) en que llegó
        self.target = ""                       # "host:puerto" al que se conecta

        self.form_message = ""        # error o aviso bajo el formulario
        self.notice = ""              # aviso temporal dentro de la mesa
        self.notice_until = 0.0
        self.waiting_reply = False    # se envió una acción y aún no hay respuesta
        self.leave_armed_until = 0.0  # doble clic para salir en plena ronda

        cx = WINDOW_WIDTH // 2
        font, small = ui.font, ui.small_font
        self.input_addr = TextInput(cx - 220, 255, 440, 46, "127.0.0.1  (vacío = este equipo)", 40)
        self.input_name = TextInput(cx - 220, 355, 440, 46, "Jugador", MAX_NAME_LEN)
        self.input_addr.active = True

        self.btn_connect = Button(cx - 110, 430, 220, 50, "CONECTAR", font, PRIMARY_COLOR, SECONDARY_COLOR)
        self.btn_back = Button(20, 20, 100, 40, "VOLVER", small, PRIMARY_COLOR, SECONDARY_COLOR)
        self.btn_leave = Button(20, 20, 130, 40, "SALIR", small, RED, SECONDARY_COLOR)
        self.btn_start = Button(cx - 170, 520, 340, 50, "INICIAR PARTIDA", font, PRIMARY_COLOR, SECONDARY_COLOR)
        self.btn_repartir = Button(cx - 160, 650, 130, 50, "REPARTIR", font, PRIMARY_COLOR, SECONDARY_COLOR)
        self.btn_me_quedo = Button(cx + 30, 650, 190, 50, "ME QUEDO", font, RED, SECONDARY_COLOR)
        self.btn_next = Button(cx - 150, 650, 300, 50, "NUEVA RONDA", font, PRIMARY_COLOR, SECONDARY_COLOR)
        self._buttons = [self.btn_connect, self.btn_back, self.btn_leave, self.btn_start,
                         self.btn_repartir, self.btn_me_quedo, self.btn_next]

        pygame.key.set_repeat(400, 35)  # mantener BORRAR pulsado

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def close(self):
        """Cierra la conexión y restablece el teclado. Llamar al salir del modo."""
        if self.net is not None:
            self.net.close()
            self.net = None
        pygame.key.set_repeat()

    def _back_to_form(self, message=""):
        if self.net is not None:
            self.net.close()
            self.net = None
        self.stage = STAGE_FORM
        self.snapshot = None
        self.my_id = None
        self.waiting_reply = False
        self.leave_armed_until = 0.0
        self.form_message = message

    def _connect(self):
        try:
            host, port = parse_address(self.input_addr.text)
        except ValueError as err:
            self.form_message = str(err)
            return
        name = self.input_name.text.strip() or "Jugador"

        self.target = f"{host}:{port}"
        self.form_message = ""
        self.net = NetworkClient()
        self.net.connect(host, port, name)
        self.stage = STAGE_CONNECTING

    # ------------------------------------------------------------------
    # Consultas sobre el estado
    # ------------------------------------------------------------------
    @property
    def phase(self):
        return self.snapshot["phase"] if self.snapshot else None

    def _player(self, player_id):
        if self.snapshot:
            for p in self.snapshot["players"]:
                if p["id"] == player_id:
                    return p
        return None

    def _is_host(self):
        return bool(self.snapshot) and self.snapshot["host_id"] == self.my_id

    def _is_my_turn(self):
        return (self.phase == PHASE_PLAYING and self.snapshot["turn_id"] == self.my_id)

    def _can_start(self):
        return self._is_host() and len(self.snapshot["players"]) >= MIN_PLAYERS

    def _seconds_left(self) -> Optional[int]:
        """Segundos restantes del turno, contando desde que llegó el estado."""
        if not self.snapshot or self.snapshot.get("time_left") is None:
            return None
        left = self.snapshot["time_left"] - (time.monotonic() - self.snapshot_at)
        return max(0, math.ceil(left))

    def _notify(self, text):
        self.notice = text
        self.notice_until = time.monotonic() + NOTICE_SECONDS

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------
    def handle_events(self, events):
        mouse_pos = pygame.mouse.get_pos()
        for button in self._buttons:
            button.check_hover(mouse_pos)

        for event in events:
            if self.stage == STAGE_FORM:
                self._events_form(event)
            elif self.stage == STAGE_CONNECTING:
                if self.btn_back.handle_event(event):  # cancelar
                    self._back_to_form()
            else:
                self._events_online(event)

    def _events_form(self, event):
        self.input_addr.handle_event(event)
        self.input_name.handle_event(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                to_name = self.input_addr.active
                self.input_addr.active = not to_name
                self.input_name.active = to_name
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._connect()
                return
        if self.btn_connect.handle_event(event):
            self._connect()
        elif self.btn_back.handle_event(event):
            self.wants_exit = True

    def _events_online(self, event):
        if self.snapshot is None:
            return
        if self.btn_leave.handle_event(event):
            self._on_leave_click()
            return

        if self.phase == PHASE_LOBBY:
            if self._can_start() and not self.waiting_reply and self.btn_start.handle_event(event):
                self._send({"type": "start"})
        elif self.phase == PHASE_PLAYING:
            if not self.waiting_reply:
                if self._is_host() and self.btn_repartir.handle_event(event):
                    self._send({"type": "draw"})
                elif self._is_my_turn() and self.btn_me_quedo.handle_event(event):
                    self._send({"type": "stay"})
        elif self.phase == PHASE_ROUND_END:
            if self._is_host() and not self.waiting_reply and self.btn_next.handle_event(event):
                self._send({"type": "start"})

    def _send(self, message):
        if self.net is not None and self.net.send(message):
            self.waiting_reply = True  # se libera con el siguiente estado o error

    def _on_leave_click(self):
        now = time.monotonic()
        if self.phase == PHASE_PLAYING and now > self.leave_armed_until:
            # En plena ronda salir es irreversible (no se puede volver a entrar
            # hasta que termine): se pide confirmar con un segundo clic.
            self.leave_armed_until = now + LEAVE_CONFIRM_SECONDS
            return
        self._back_to_form()

    # ------------------------------------------------------------------
    # Red
    # ------------------------------------------------------------------
    def update(self):
        now = time.monotonic()
        if self.notice and now > self.notice_until:
            self.notice = ""
        if self.net is None:
            return
        for message in self.net.poll():
            self._on_message(message)
            if self.net is None:  # el mensaje provocó volver al formulario
                break

    def _on_message(self, message):
        kind = message.get("type")
        if kind == "welcome":
            self.my_id = message.get("id")
            self.stage = STAGE_ONLINE
        elif kind == "state":
            self.snapshot = message
            self.snapshot_at = time.monotonic()
            self.waiting_reply = False
            if message.get("phase") != PHASE_PLAYING:
                self.leave_armed_until = 0.0
        elif kind == "error":
            self.waiting_reply = False
            text = message.get("message", "Error del servidor.")
            if self.stage == STAGE_ONLINE:
                self._notify(text)
            else:  # el servidor rechazó la entrada (mesa llena, ronda en curso...)
                self._back_to_form(text)
        elif kind == "_failed":
            self._back_to_form(message.get("message", "No se pudo conectar."))
        elif kind == "_closed":
            self._back_to_form("Se perdió la conexión con el servidor.")

    # ------------------------------------------------------------------
    # Dibujo
    # ------------------------------------------------------------------
    def draw(self):
        """Dibuja la pantalla actual (quien llama limpia antes y hace flip después)."""
        if self.stage == STAGE_FORM:
            self._draw_form()
        elif self.stage == STAGE_CONNECTING or self.snapshot is None:
            self._draw_connecting()
        elif self.phase == PHASE_LOBBY:
            self._draw_lobby()
        else:
            self._draw_table()

        if self.notice:
            self.ui.draw_text(self.notice, self.ui.small_font, RED,
                              WINDOW_WIDTH // 2, 730, center=True)

    def _draw_button(self, button, enabled=True):
        if enabled:
            button.draw(self.screen)
            return
        saved = (button.color, button.hover_color)
        button.color = button.hover_color = GRAY
        button.draw(self.screen)
        button.color, button.hover_color = saved

    def _draw_form(self):
        ui, cx = self.ui, WINDOW_WIDTH // 2
        ui.draw_text("SIGLO", ui.title_font, TEXT_COLOR, cx, 90, center=True)
        ui.draw_text("Multijugador", ui.font, TEXT_COLOR, cx, 150, center=True)

        ui.draw_text("Servidor (IP o IP:puerto)", ui.small_font, TEXT_COLOR, cx - 220, 222)
        self.input_addr.draw(self.screen, ui.font)
        ui.draw_text("Tu nombre", ui.small_font, TEXT_COLOR, cx - 220, 322)
        self.input_name.draw(self.screen, ui.font)

        self.btn_connect.draw(self.screen)
        self.btn_back.draw(self.screen)
        if self.form_message:
            ui.draw_text(self.form_message, ui.small_font, RED, cx, 510, center=True)
        ui.draw_text("Tab: cambiar de campo   ·   Enter: conectar",
                     ui.small_font, GRAY, cx, 720, center=True)

    def _draw_connecting(self):
        ui, cx = self.ui, WINDOW_WIDTH // 2
        ui.draw_text("SIGLO", ui.title_font, TEXT_COLOR, cx, 100, center=True)
        dots = "." * (1 + (pygame.time.get_ticks() // 400) % 3)
        ui.draw_text(f"Conectando a {self.target}{dots}", ui.font, TEXT_COLOR, cx, 300, center=True)
        self.btn_back.draw(self.screen)

    def _draw_lobby(self):
        ui, cx = self.ui, WINDOW_WIDTH // 2
        players = self.snapshot["players"]
        ui.draw_table_felt()
        ui.draw_table_header("SIGLO", subtitle="Sala de espera",
                              corner_text=f"{len(players)}/{self.snapshot['max_players']}")

        for i, p in enumerate(players):
            y = 190 + i * 46
            board_ui.draw_avatar(self.screen, ui.small_font, p["name"], (cx - 170, y), radius=18)
            label = p["name"]
            tags = []
            if p["id"] == self.snapshot["host_id"]:
                tags.append("anfitrión")
            if p["id"] == self.my_id:
                tags.append("tú")
            if tags:
                label += "  ·  " + " · ".join(tags)
            color = board_ui.GOLD if p["id"] == self.my_id else board_ui.CREAM_TEXT
            ui.draw_text(label, ui.font, color, cx - 140, y - 16, center=False)

        self.btn_leave.text = "SALIR"
        self.btn_leave.draw(self.screen)
        if self._is_host():
            enough = self._can_start()
            self._draw_button(self.btn_start, enough and not self.waiting_reply)
            if not enough:
                ui.draw_text(f"Se necesitan al menos {MIN_PLAYERS} jugadores",
                             ui.small_font, board_ui.CREAM_TEXT_DIM, cx, 590, center=True)
        else:
            host = self._player(self.snapshot["host_id"])
            name = host["name"] if host else "el anfitrión"
            ui.draw_text(f"Esperando a que {name} inicie la partida...",
                         ui.small_font, board_ui.CREAM_TEXT_DIM, cx, 540, center=True)

    def _draw_table(self):
        ui, cx = self.ui, WINDOW_WIDTH // 2
        snap = self.snapshot
        ui.draw_table_felt()
        ui.draw_table_header("SIGLO", corner_text=f"Ronda {snap['round']}", y=40)

        self._draw_board()

        if self.phase == PHASE_PLAYING:
            self._draw_turn_info()
        else:
            self._draw_round_result()

        # Botón de salir (pide confirmar en plena ronda)
        armed = time.monotonic() < self.leave_armed_until
        self.btn_leave.text = "¿SEGURO?" if armed else "SALIR"
        self.btn_leave.draw(self.screen)

    def _draw_board(self):
        players = self.snapshot["players"]
        turn_id = self.snapshot["turn_id"]
        winner_ids = set(self.snapshot["winner_ids"])
        rects = board_ui.card_rects(len(players))

        for p, rect in zip(players, rects):
            board_ui.draw_player_card(
                self.screen, self.ui, rect,
                name=p["name"],
                score=p["score"],
                status=p["status"],
                balls=p["balls"],
                is_turn=(p["id"] == turn_id),
                is_winner=(p["id"] in winner_ids),
                is_me=(p["id"] == self.my_id),
                connected=p["connected"],
                wins=p["wins"],
                hidden=p.get("hidden", False),
            )

    def _draw_turn_info(self):
        ui, cx = self.ui, WINDOW_WIDTH // 2
        if self._is_my_turn():
            ui.draw_text("¡ES TU TURNO!", ui.font, board_ui.GOLD, cx, 580, center=True)
        else:
            current = self._player(self.snapshot["turn_id"])
            name = current["name"] if current else "..."
            ui.draw_text(f"Turno de {name}", ui.font, board_ui.CREAM_TEXT, cx, 580, center=True)

        seconds = self._seconds_left()
        if seconds is not None:
            color = (230, 110, 90) if seconds <= 5 else board_ui.CREAM_TEXT_DIM
            ui.draw_text(f"Tiempo: {seconds} s", ui.small_font, color, cx, 615, center=True)

        show_repartir = self._is_host()
        show_me_quedo = self._is_my_turn()
        cx_pair = WINDOW_WIDTH // 2
        if show_repartir and show_me_quedo:
            self.btn_repartir.rect.x = cx_pair - 160
            self.btn_me_quedo.rect.x = cx_pair + 30
        elif show_me_quedo:
            self.btn_me_quedo.rect.x = cx_pair - self.btn_me_quedo.rect.width // 2
        elif show_repartir:
            self.btn_repartir.rect.x = cx_pair - self.btn_repartir.rect.width // 2
        if show_repartir:
            self._draw_button(self.btn_repartir, not self.waiting_reply)
        if show_me_quedo:
            self._draw_button(self.btn_me_quedo, not self.waiting_reply)

    def _draw_round_result(self):
        ui, cx = self.ui, WINDOW_WIDTH // 2
        winner_ids = set(self.snapshot["winner_ids"])
        names = [p["name"] for p in self.snapshot["players"] if p["id"] in winner_ids]
        if names:
            text, color = "Ganador(es): " + ", ".join(names), board_ui.GOLD
        else:
            text, color = "Todos se pasaron de 100 (ME FUI). Sin ganadores.", (230, 120, 120)
        font = ui.font if ui.font.size(text)[0] <= WINDOW_WIDTH - 40 else ui.small_font
        ui.draw_text(text, font, color, cx, 585, center=True)

        if self._is_host():
            self._draw_button(self.btn_next, not self.waiting_reply)
        else:
            host = self._player(self.snapshot["host_id"])
            name = host["name"] if host else "el anfitrión"
            ui.draw_text(f"Esperando a que {name} inicie la siguiente ronda...",
                         ui.small_font, board_ui.CREAM_TEXT_DIM, cx, 675, center=True)

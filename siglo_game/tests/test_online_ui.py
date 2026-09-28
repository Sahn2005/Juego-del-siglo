"""Pruebas del cliente pygame (sin ventana real) contra un servidor en un hilo."""
import asyncio
import os
import threading
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from helpers import fixed_deck
from src.game import Game
from src.match import Match
from src.online import OnlineGame
from src.server import SigloServer
from src.ui import UI
from src.utils import STATE_MENU, STATE_ONLINE


@pytest.fixture(scope="module", autouse=True)
def pygame_session():
    pygame.init()
    pygame.display.set_mode((1024, 768))
    yield
    pygame.quit()


class ServerThread:
    """Servidor real corriendo en su propio hilo/loop."""

    def __init__(self, *deck_values):
        self.loop = asyncio.new_event_loop()
        self.server = SigloServer("127.0.0.1", 0, Match(deck_factory=fixed_deck(*deck_values)))
        ready = threading.Event()

        def run():
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.server.start())
            ready.set()
            self.loop.run_forever()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        assert ready.wait(5)
        self.port = self.server.port

    def stop(self):
        if not self.thread.is_alive():
            return
        asyncio.run_coroutine_threadsafe(self.server.stop(), self.loop).result(5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)


@pytest.fixture
def server(request):
    st = ServerThread(*getattr(request, "param", (50, 60, 49)))
    yield st
    st.stop()


class Player:
    def __init__(self):
        self.surface = pygame.Surface((1024, 768))
        self.game = OnlineGame(self.surface, UI(self.surface))

    def until(self, cond, timeout=4.0):
        end = time.time() + timeout
        while time.time() < end:
            self.game.update()
            if cond():
                return
            time.sleep(0.01)
        raise AssertionError(f"timeout: stage={self.game.stage} phase={self.game.phase} "
                             f"msg={self.game.form_message!r}")

    def click(self, button, monkeypatch):
        pos = button.rect.center
        monkeypatch.setattr(pygame.mouse, "get_pos", lambda: pos)
        self.game.handle_events([pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)])

    def type(self, text):
        for ch in text:
            self.game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=0, unicode=ch)])

    def connect(self, port, name):
        self.game.input_addr.text = f"127.0.0.1:{port}"
        self.game.input_name.text = name
        self.game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode="\r")])
        self.until(lambda: self.game.phase is not None)

    def draw(self):
        self.surface.fill((0, 0, 0))
        self.game.draw()  # no debe lanzar en ninguna pantalla


def test_form_validation_and_connection_refused(monkeypatch):
    p = Player()
    p.draw()
    p.type("127.0.0.1:abc")
    p.game.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode="\r")])
    assert "número" in p.game.form_message

    p.game.input_addr.text = "127.0.0.1:1"
    p.click(p.game.btn_connect, monkeypatch)
    assert p.game.stage == "CONNECTING"
    p.draw()
    p.until(lambda: p.game.stage == "FORM")
    assert "rechazó" in p.game.form_message
    p.draw()
    p.game.close()


def test_two_players_play_a_round(server, monkeypatch):
    # Viras: Ana 50, Luis 60. Ana saca 49 = 99 (SIGLO). Luis se planta.
    ana, luis = Player(), Player()
    ana.connect(server.port, "Ñandú")
    luis.connect(server.port, "Luis")
    ana.until(lambda: len(ana.game.snapshot["players"]) == 2)
    ana.draw(); luis.draw()

    # Solo el anfitrión puede iniciar
    assert ana.game._can_start() and not luis.game._is_host()
    ana.click(ana.game.btn_start, monkeypatch)
    ana.until(lambda: ana.game.phase == "PLAYING")
    luis.until(lambda: luis.game.phase == "PLAYING")
    assert ana.game._is_my_turn() and not luis.game._is_my_turn()
    ana.draw(); luis.draw()

    # Luis pulsa BOLA fuera de turno: el cliente ni lo envía
    luis.click(luis.game.btn_bola, monkeypatch)
    assert not luis.game.waiting_reply

    ana.click(ana.game.btn_bola, monkeypatch)
    assert ana.game.waiting_reply  # botones bloqueados hasta que responda el servidor
    ana.until(lambda: not ana.game.waiting_reply)
    luis.until(lambda: luis.game._is_my_turn())

    luis.click(luis.game.btn_me_quedo, monkeypatch)
    for pl in (ana, luis):
        pl.until(lambda pl=pl: pl.game.phase == "ROUND_END")
        pl.draw()
    assert ana.game.snapshot["winner_ids"] == [ana.game.my_id]
    assert ana.game._player(ana.game.my_id)["status"] == "SIGLO"

    ana.game.close(); luis.game.close()


@pytest.mark.parametrize("server", [(10, 20)], indirect=True)
def test_leaving_mid_round_needs_confirmation(server, monkeypatch):
    ana, luis = Player(), Player()
    ana.connect(server.port, "Ana")
    luis.connect(server.port, "Luis")
    ana.until(lambda: len(ana.game.snapshot["players"]) == 2)
    ana.click(ana.game.btn_start, monkeypatch)
    ana.until(lambda: ana.game.phase == "PLAYING")
    luis.until(lambda: luis.game.phase == "PLAYING")

    luis.click(luis.game.btn_leave, monkeypatch)       # 1er clic: solo pide confirmar
    assert luis.game.stage == "ONLINE"
    luis.draw()
    luis.click(luis.game.btn_leave, monkeypatch)       # 2º clic: sale
    assert luis.game.stage == "FORM"

    ana.until(lambda: not ana.game._player(2)["connected"])
    assert ana.game._player(2)["status"] == "ME_QUEDO"
    ana.game.close(); luis.game.close()


@pytest.mark.parametrize("server", [(10, 20)], indirect=True)
def test_join_refused_mid_round_shows_reason(server, monkeypatch):
    ana, luis, late = Player(), Player(), Player()
    ana.connect(server.port, "Ana")
    luis.connect(server.port, "Luis")
    ana.until(lambda: len(ana.game.snapshot["players"]) == 2)
    ana.click(ana.game.btn_start, monkeypatch)
    ana.until(lambda: ana.game.phase == "PLAYING")

    late.game.input_addr.text = f"127.0.0.1:{server.port}"
    late.click(late.game.btn_connect, monkeypatch)
    late.until(lambda: late.game.stage == "FORM")
    assert "en curso" in late.game.form_message  # el motivo real, no "conexión perdida"
    for pl in (ana, luis, late):
        pl.game.close()


def test_server_going_down_returns_to_form(server):
    p = Player()
    p.connect(server.port, "Ana")
    server.stop()
    p.until(lambda: p.game.stage == "FORM")
    assert "conexión" in p.game.form_message
    p.game.close()


def test_main_menu_opens_and_closes_online_mode(monkeypatch):
    screen = pygame.display.get_surface()
    game = Game(screen)
    assert game.state == STATE_MENU

    pos = game.btn_online.rect.center
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: pos)
    game.handle_events([pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)])
    assert game.state == STATE_ONLINE and game.online is not None
    game.update(); game.render()

    back = game.online.btn_back.rect.center
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: back)
    game.handle_events([pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=back)])
    assert game.state == STATE_MENU and game.online is None
    game.render()


def test_main_menu_single_player_still_works(monkeypatch):
    screen = pygame.display.get_surface()
    game = Game(screen)
    pos = game.btn_play.rect.center
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: pos)
    game.handle_events([pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)])
    assert len(game.players) == 3 and game.players[0].name == "Jugador 1"
    game.update(); game.render()

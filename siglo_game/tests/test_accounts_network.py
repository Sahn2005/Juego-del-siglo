"""Registro, login y estadísticas de punta a punta (TCP y WebSocket)."""
import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from helpers import fixed_deck
from src.database import AccountDatabase
from src.match import Match
from src.protocol import PHASE_PLAYING, PHASE_ROUND_END
from src.server import SigloServer
from src.webapp import build_app
from test_network import FakeClient
from test_webapp import WsClient


async def tcp(server, **first):
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    c = FakeClient(reader, writer)
    c.send(**first)
    return c


def run(scenario, *deck_values, store=None):
    async def main():
        server = SigloServer("127.0.0.1", 0, Match(deck_factory=fixed_deck(*deck_values)))
        server.database = store or AccountDatabase(":memory:")
        await server.start()
        try:
            await asyncio.wait_for(scenario(server), timeout=10)
        finally:
            await server.stop()
    asyncio.run(main())


def test_register_then_welcome_has_stats():
    async def scenario(server):
        a = await tcp(server, type="register", username="Ana", password="secreto123")
        w = await a.recv_until(lambda m: m["type"] == "welcome")
        assert w["account"] is True
        assert w["stats"] == {"games_played": 0, "games_won": 0}
        s = await a.wait_state(lambda s: len(s["players"]) == 1)
        assert s["players"][0]["name"] == "Ana"
        a.close()
    run(scenario)


def test_register_errors_and_login():
    async def scenario(server):
        a = await tcp(server, type="register", username="Ana", password="secreto123")
        await a.recv_until(lambda m: m["type"] == "welcome")
        a.close()
        await asyncio.sleep(0.05)

        dup = await tcp(server, type="register", username="ana", password="otraclave123")
        assert "ya está registrado" in (await dup.recv_until(lambda m: m["type"] == "error"))["message"]
        short = await tcp(server, type="register", username="Bo", password="secreto123")
        assert (await short.recv_until(lambda m: m["type"] == "error"))["message"]
        weak = await tcp(server, type="register", username="Carlos", password="12")
        assert "contraseña" in (await weak.recv_until(lambda m: m["type"] == "error"))["message"]
        bad = await tcp(server, type="login", username="Ana", password="mala")
        assert "incorrectos" in (await bad.recv_until(lambda m: m["type"] == "error"))["message"]
        ghost = await tcp(server, type="login", username="Nadie", password="secreto123")
        assert "incorrectos" in (await ghost.recv_until(lambda m: m["type"] == "error"))["message"]

        ok = await tcp(server, type="login", username="ANA", password="secreto123")
        w = await ok.recv_until(lambda m: m["type"] == "welcome")
        assert w["account"] is True
        ok.close()
    run(scenario)


def test_same_account_cannot_sit_twice():
    async def scenario(server):
        a = await tcp(server, type="register", username="Ana", password="secreto123")
        await a.recv_until(lambda m: m["type"] == "welcome")
        again = await tcp(server, type="login", username="Ana", password="secreto123")
        err = await again.recv_until(lambda m: m["type"] == "error")
        assert "ya está en esta mesa" in err["message"]
        a.close()
    run(scenario)


def test_guest_gets_no_account_data():
    async def scenario(server):
        g = await tcp(server, type="join", name="Invitado")
        w = await g.recv_until(lambda m: m["type"] == "welcome")
        assert "stats" not in w and "account" not in w
        g.close()
    run(scenario)


def test_stats_saved_after_round_and_guests_ignored():
    # Ana (cuenta) 50 vs Luis (invitado) 60: gana Luis. Segunda ronda: 70 vs 40... 
    async def scenario(server):
        a = await tcp(server, type="register", username="Ana", password="secreto123")
        await a.recv_until(lambda m: m["type"] == "welcome")
        b = await tcp(server, type="join", name="Luis")
        await b.recv_until(lambda m: m["type"] == "welcome")
        await a.wait_state(lambda s: len(s["players"]) == 2)

        a.send(type="start")
        await a.wait_state(lambda s: s["phase"] == PHASE_PLAYING)
        a.send(type="stay")
        await b.wait_state(lambda s: s["turn_id"] == b.id)
        b.send(type="stay")
        st = await a.recv_until(lambda m: m["type"] == "stats")
        assert st == {"type": "stats", "games_played": 1, "games_won": 0}
        a.close(); b.close()
        await asyncio.sleep(0.05)
        # persiste: otro login ve las estadísticas
        again = await tcp(server, type="login", username="Ana", password="secreto123")
        w = await again.recv_until(lambda m: m["type"] == "welcome")
        assert w["stats"] == {"games_played": 1, "games_won": 0}
        again.close()
    run(scenario, 50, 60)


def test_winner_counts_a_win():
    async def scenario(server):
        a = await tcp(server, type="register", username="Ana", password="secreto123")
        await a.recv_until(lambda m: m["type"] == "welcome")
        b = await tcp(server, type="register", username="Luis", password="secreto123")
        await b.recv_until(lambda m: m["type"] == "welcome")
        await a.wait_state(lambda s: len(s["players"]) == 2)
        a.send(type="start")
        await a.wait_state(lambda s: s["phase"] == PHASE_PLAYING)
        a.send(type="stay")
        await b.wait_state(lambda s: s["turn_id"] == b.id)
        b.send(type="stay")
        sa = await a.recv_until(lambda m: m["type"] == "stats")
        sb = await b.recv_until(lambda m: m["type"] == "stats")
        assert (sa["games_won"], sb["games_won"]) == (0, 1)  # 60 le gana a 50
        assert sa["games_played"] == sb["games_played"] == 1
        a.close(); b.close()
    run(scenario, 50, 60)


# --------------------------- WebSocket ---------------------------------
@pytest.fixture
async def web():
    server = SigloServer("127.0.0.1", 0, Match(deck_factory=fixed_deck(50, 60)))
    server.database = AccountDatabase(":memory:")
    tc = TestClient(TestServer(build_app(server)))
    await tc.start_server()
    yield tc
    await tc.close()
    await server.stop()


async def test_websocket_register_login_and_stats(web):
    a = WsClient(await web.ws_connect("/ws"))
    await a.send(type="register", username="Ana", password="secreto123")
    w = await a.recv_until(lambda m: m["type"] == "welcome")
    assert w["stats"] == {"games_played": 0, "games_won": 0}

    b = WsClient(await web.ws_connect("/ws"))
    await b.send(type="join", name="Luis")
    await b.recv_until(lambda m: m["type"] == "welcome")
    await a.wait_state(lambda s: len(s["players"]) == 2)
    await a.send(type="start")
    await a.wait_state(lambda s: s["phase"] == PHASE_PLAYING)
    await a.send(type="stay")
    await b.wait_state(lambda s: s["turn_id"] == b.id)
    await b.send(type="stay")
    st = await a.recv_until(lambda m: m["type"] == "stats")
    assert st["games_played"] == 1


async def test_websocket_bad_login_gets_error(web):
    c = WsClient(await web.ws_connect("/ws"))
    await c.send(type="login", username="Nadie", password="secreto123")
    err = await c.recv_until(lambda m: m["type"] == "error")
    assert "incorrectos" in err["message"]

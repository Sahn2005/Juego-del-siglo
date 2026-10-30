"""Pruebas del transporte WebSocket (para el cliente del navegador).

Usa aiohttp.test_utils para levantar la app real en un puerto de pruebas y
un ClientSession real para conectarse, igual que haría un navegador. No
hace falta un navegador de verdad: el protocolo (JSON por mensaje) es el
mismo sin importar quién lo hable.
"""
import asyncio
import json

import pytest
from aiohttp import ClientSession, DummyCookieJar, WSMsgType
from aiohttp.test_utils import TestClient, TestServer

from helpers import fixed_deck
from src.database import AccountDatabase
from src.match import Match
from src.protocol import PHASE_LOBBY, PHASE_PLAYING, PHASE_ROUND_END, decode, encode
from src.server import SigloServer
from src.webapp import build_app


def make_app(*deck_values, turn_seconds=30.0, database_path=None):
    match = Match(deck_factory=fixed_deck(*deck_values), turn_seconds=turn_seconds)
    server = SigloServer("127.0.0.1", 0, match)
    server.database = AccountDatabase(database_path)
    return server, build_app(server)


class WsClient:
    """Habla el protocolo sobre un WebSocket real, como el navegador."""

    def __init__(self, ws):
        self.ws = ws
        self.id = None
        self.state = None

    async def send(self, **message):
        await self.ws.send_str(json.dumps(message))

    async def recv(self, timeout=2.0):
        msg = await asyncio.wait_for(self.ws.receive(), timeout)
        if msg.type != WSMsgType.TEXT:
            return None
        data = json.loads(msg.data)
        if data.get("type") == "welcome":
            self.id = data["id"]
        elif data.get("type") == "state":
            self.state = data
        return data

    async def recv_until(self, predicate, timeout=2.0):
        while True:
            msg = await self.recv(timeout)
            if msg is None:
                raise AssertionError("conexión cerrada antes de lo esperado")
            if predicate(msg):
                return msg

    async def wait_state(self, predicate, timeout=2.0):
        return await self.recv_until(lambda m: m.get("type") == "state" and predicate(m), timeout)


@pytest.fixture
async def client(request, tmp_path):
    deck_values = getattr(request, "param", (50, 60, 49))
    server, app = make_app(
        *deck_values,
        turn_seconds=getattr(request, "turn_seconds", 30.0),
        database_path=str(tmp_path / "siglo-test.sqlite3"),
    )
    await server.start()  # también el TCP, para las pruebas de mesa compartida
    test_server = TestServer(app)
    tc = TestClient(test_server)
    await tc.start_server()
    tc.server_obj = server
    yield tc
    await tc.close()
    await server.stop()


async def join_two(client, names=("Ana", "Luis")):
    ws_a = await client.ws_connect("/ws")
    a = WsClient(ws_a)
    await a.send(type="join", name=names[0])
    await a.recv_until(lambda m: m["type"] == "welcome")

    ws_b = await client.ws_connect("/ws")
    b = WsClient(ws_b)
    await b.send(type="join", name=names[1])
    await b.recv_until(lambda m: m["type"] == "welcome")

    await a.wait_state(lambda s: len(s["players"]) == 2)
    await b.wait_state(lambda s: len(s["players"]) == 2)
    return a, b


async def join_many(client, names):
    clients = []
    for name in names:
        ws = await client.ws_connect("/ws")
        c = WsClient(ws)
        await c.send(type="join", name=name)
        await c.recv_until(lambda m: m["type"] == "welcome")
        clients.append(c)
    for c in clients:
        await c.wait_state(lambda s: len(s["players"]) == len(clients))
    return clients


# ---------------------------------------------------------------- estáticos

async def test_serves_index_and_assets(client):
    resp = await client.get("/")
    assert resp.status == 200
    text = await resp.text()
    assert "SIGLO" in text and "app.js" in text

    resp = await client.get("/app.js")
    assert resp.status == 200
    resp = await client.get("/style.css")
    assert resp.status == 200


async def test_static_files_are_revalidated_not_cached_blindly(client):
    for path in ("/", "/app.js", "/style.css"):
        resp = await client.get(path)
        assert resp.headers["Cache-Control"] == "no-cache", path
    # y aun así una segunda petición con ETag responde 304 (no reenvía el archivo)
    first = await client.get("/app.js")
    etag = first.headers.get("ETag")
    assert etag
    again = await client.get("/app.js", headers={"If-None-Match": etag})
    assert again.status == 304


async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status == 200
    body = await resp.json()
    assert body["ok"] is True and body["jugadores"] == 0 and body["fase"] == PHASE_LOBBY
    assert body["cuentas"] in ("sqlite", "postgresql")
    assert body["cuentas_persistentes"] == (body["cuentas"] == "postgresql")


async def test_register_login_and_logout(client):
    response = await client.post(
        "/api/register",
        json={"username": "Jugadora", "password": "secreto123"},
    )
    assert response.status == 200
    assert response.cookies["siglo_session"]["httponly"]
    assert (await response.json())["account"]["username"] == "Jugadora"

    response = await client.get("/api/history")
    body = await response.json()
    assert response.status == 200
    assert body["stats"] == {"played": 0, "wins": 0, "losses": 0}
    assert body["games"] == []

    response = await client.post(
        "/api/register",
        json={"username": "jugadora", "password": "secreto123"},
    )
    assert response.status == 400

    await client.post("/api/logout")
    assert (await client.get("/api/history")).status == 401
    response = await client.post(
        "/api/login",
        json={"username": "JUGADORA", "password": "secreto123"},
    )
    assert response.status == 200


@pytest.mark.parametrize("client", [(50, 60, 49)], indirect=True)
async def test_authenticated_round_is_saved_to_account_history(client):
    response = await client.post(
        "/api/register",
        json={"username": "AnaJuego", "password": "secreto123"},
    )
    assert response.status == 200

    ws_a = await client.ws_connect("/ws")
    a = WsClient(ws_a)
    await a.send(type="join", name="Nombre falso")
    await a.recv_until(lambda message: message["type"] == "welcome")

    guest_session = ClientSession(cookie_jar=DummyCookieJar())
    ws_b = await guest_session.ws_connect(client.make_url("/ws"))
    b = WsClient(ws_b)
    await b.send(type="join", name="Luis")
    await b.recv_until(lambda message: message["type"] == "welcome")
    await a.wait_state(lambda state: len(state["players"]) == 2)

    lobby = a.state
    assert next(player for player in lobby["players"] if player["id"] == a.id)["name"] == "AnaJuego"
    await a.send(type="start")
    await a.wait_state(lambda state: state["phase"] == PHASE_PLAYING)
    await a.send(type="draw")
    state = await a.wait_state(
        lambda state: next(player for player in state["players"] if player["id"] == a.id)["status"] == "SIGLO"
    )
    assert state["last_action"] == {
        "event_id": 1, "name": "AnaJuego", "status": "SIGLO",
    }
    await b.send(type="stay")
    state = await a.wait_state(lambda state: state["phase"] == PHASE_ROUND_END)
    assert state["last_action"] == {
        "event_id": 2, "name": "Luis", "status": "ME_QUEDO",
    }

    history = await (await client.get("/api/history")).json()
    assert history["stats"] == {"played": 1, "wins": 1, "losses": 0}
    assert history["games"][0]["score"] == 99
    assert history["games"][0]["status"] == "SIGLO"
    assert history["games"][0]["result"] == "Victoria"
    assert history["games"][0]["opponents"] == ["Luis"]
    await ws_a.close()
    await ws_b.close()
    await guest_session.close()


# ---------------------------------------------------------------- websocket, una mesa

async def test_join_and_lobby_state(client):
    a, b = await join_two(client)
    assert a.id != b.id
    assert a.state["phase"] == PHASE_LOBBY
    assert a.state["host_id"] == a.id
    assert [p["name"] for p in b.state["players"]] == ["Ana", "Luis"]


async def test_accented_name_survives_the_wire(client):
    ws = await client.ws_connect("/ws")
    c = WsClient(ws)
    await c.send(type="join", name="Ñandú")
    state = await c.wait_state(lambda s: len(s["players"]) == 1)
    assert state["players"][0]["name"] == "Ñandú"


@pytest.mark.parametrize("client", [(50, 60, 49)], indirect=True)
async def test_full_round(client):
    a, b = await join_two(client)
    await a.send(type="start")
    s = await a.wait_state(lambda s: s["phase"] == PHASE_PLAYING)
    assert s["turn_id"] == a.id
    assert s["host_deals"] is False  # solo 2 jugadores: autoservicio

    await a.send(type="draw")  # Ana pide su propia ficha en su propio turno
    s = await a.wait_state(
        lambda s: next(p for p in s["players"] if p["id"] == a.id)["status"] == "SIGLO"
    )
    me = next(p for p in s["players"] if p["id"] == a.id)
    assert s["turn_id"] == b.id and me["score"] == 99

    await b.send(type="stay")
    s = await a.wait_state(lambda s: s["phase"] == PHASE_ROUND_END)
    assert s["winner_ids"] == [a.id]
    assert all(p["hidden"] is False for p in s["players"])


async def test_two_players_draw_out_of_turn_errors_the_offender(client):
    """Con 2 jugadores no hay repartidor: pedir ficha fuera de turno es el
    mismo error de siempre ("no es tu turno"), no uno de permisos."""
    a, b = await join_two(client)
    await a.send(type="start")
    await b.wait_state(lambda s: s["phase"] == PHASE_PLAYING)

    await b.send(type="draw")
    err = await b.recv_until(lambda m: m["type"] == "error")
    assert "turno" in err["message"]

    await a.send(type="stay")
    s = await a.wait_state(lambda s: s["turn_id"] == b.id)
    assert s["players"][0]["status"] == "ME_QUEDO"


@pytest.mark.parametrize("client", [(10, 20, 30, 5, 7)], indirect=True)
async def test_non_host_cannot_deal_with_three_or_more(client):
    a, b, c = await join_many(client, ("Ana", "Luis", "Marta"))
    await a.send(type="start")
    s = await c.wait_state(lambda s: s["phase"] == PHASE_PLAYING)
    assert s["host_deals"] is True

    await b.send(type="draw")  # el anfitrión es el único que puede repartir
    err = await b.recv_until(lambda m: m["type"] == "error")
    assert "repartidor" in err["message"]

    await a.send(type="draw")  # la anfitriona puede repartirse en su turno
    await a.wait_state(lambda s: s["players"][0]["balls"] != [10])
    await a.send(type="stay")
    await a.wait_state(lambda s: s["turn_id"] == b.id)

    await b.send(type="request_draw")
    await b.wait_state(lambda s: s.get("draw_request") and s["draw_request"]["player_id"] == b.id)
    s = await a.wait_state(lambda s: s.get("draw_request") and s["draw_request"]["player_id"] == b.id)
    assert s["draw_request"]["name"] == "Luis"

    await a.send(type="draw")
    s = await b.wait_state(
        lambda s: next(player for player in s["players"] if player["id"] == b.id)["balls"] == [20, 7]
    )
    assert s["draw_request"] is None


async def test_out_of_turn_stay_only_errors_the_offender(client):
    a, b = await join_two(client)
    await a.send(type="start")
    await b.wait_state(lambda s: s["phase"] == PHASE_PLAYING)

    await b.send(type="stay")
    err = await b.recv_until(lambda m: m["type"] == "error")
    assert "turno" in err["message"]


async def test_table_full_error_then_closes(client):
    a, b = await join_two(client)
    server = client.server_obj
    server.match.max_players = 2
    ws = await client.ws_connect("/ws")
    c = WsClient(ws)
    await c.send(type="join", name="Tarde")
    err = await c.recv_until(lambda m: m["type"] == "error")
    assert "llena" in err["message"]
    closed = await c.recv()
    assert closed is None  # el servidor cierra la conexión


async def test_garbage_frame_disconnects_only_the_offender(client):
    a, b = await join_two(client)
    await b.ws.send_str("esto no es json")
    closed = await b.recv()
    assert closed is None
    s = await a.wait_state(lambda s: len(s["players"]) == 1)
    assert s["players"][0]["name"] == "Ana"


async def test_disconnect_mid_turn_seen_by_others(client):
    a, b = await join_two(client)
    await a.send(type="start")
    await b.wait_state(lambda s: s["phase"] == PHASE_PLAYING)

    await a.ws.close()
    s = await b.wait_state(lambda s: s["turn_id"] == b.id)
    ana = s["players"][0]
    assert ana["connected"] is False
    assert ana["status"] == "ME_QUEDO"
    assert s["host_id"] == b.id


async def test_turn_timeout_over_websocket():
    server, app = make_app(10, 20, turn_seconds=0.3)
    test_server = TestServer(app)
    tc = TestClient(test_server)
    await tc.start_server()
    try:
        a, b = await join_two(tc)
        await a.send(type="start")
        await a.wait_state(lambda s: s["phase"] == PHASE_PLAYING)
        s = await b.wait_state(lambda s: s["turn_id"] == b.id, timeout=3)
        assert s["players"][0]["status"] == "ME_QUEDO"
    finally:
        await tc.close()


# ---------------------------------------------------------------- mesa compartida TCP + WS

async def test_tcp_and_websocket_share_the_same_table(client):
    server = client.server_obj

    ws = await client.ws_connect("/ws")
    web_player = WsClient(ws)
    await web_player.send(type="join", name="Ana")
    await web_player.recv_until(lambda m: m["type"] == "welcome")
    ana_id = web_player.id

    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    writer.write(encode({"type": "join", "name": "Luis"}))
    welcome = decode(await reader.readline())
    luis_id = welcome["id"]

    await web_player.wait_state(lambda s: len(s["players"]) == 2)
    state_tcp = decode(await reader.readline())
    while len(state_tcp["players"]) != 2:
        state_tcp = decode(await reader.readline())

    await web_player.send(type="start")
    s = await web_player.wait_state(lambda s: s["phase"] == PHASE_PLAYING)
    assert s["turn_id"] == ana_id

    await web_player.send(type="stay")
    s = await web_player.wait_state(lambda s: s["turn_id"] == luis_id)
    assert s["players"][0]["status"] == "ME_QUEDO"

    writer.write(encode({"type": "stay"}))
    state_tcp = decode(await reader.readline())
    while state_tcp["phase"] != PHASE_ROUND_END:
        state_tcp = decode(await reader.readline())
    assert set(state_tcp["winner_ids"]) <= {ana_id, luis_id}

    writer.close()


async def test_serves_3d_view_assets(client):
    """La vista 3D del navegador necesita estos archivos estáticos."""
    for path in ("/mesa3d.js", "/vendor/three.min.js"):
        resp = await client.get(path)
        assert resp.status == 200, path
        assert len(await resp.read()) > 1000
    html = await (await client.get("/")).text()
    assert "btn-view" in html and "mesa3d.js" in html
